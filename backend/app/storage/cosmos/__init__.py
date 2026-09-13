import logging
import time
from uuid import uuid4

from azure.core.exceptions import ServiceRequestError, ServiceResponseError
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from fastapi.encoders import jsonable_encoder

from ..interfaces import StorageConflict, StorageLimit, StorageUnavailable
from ..receipts import open_result, seal
from .documents import SCHEMA_VERSION, decode, document, encode, encoded, preflight

logger = logging.getLogger("lex.storage")


class CosmosStore:
    def __init__(self, settings, *, container=None):
        self.settings = settings
        self.club = settings.cosmos_club_id
        self.client = self.credential = None
        if container is not None:
            self.container = container
            return
        if settings.cosmos_auth_mode == "emulator":
            credential = settings.cosmos_key.get_secret_value()
        elif settings.cosmos_auth_mode == "managed_identity":
            self.credential = ManagedIdentityCredential(client_id=settings.cosmos_managed_identity_client_id)
            credential = self.credential
        else:
            self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            credential = self.credential
        self.client = CosmosClient(
            settings.cosmos_endpoint,
            credential=credential,
            consistency_level="Strong",
            connection_timeout=5,
            timeout=15,
            retry_total=2,
            retry_backoff_max=2,
            enable_diagnostics_logging=False,
        )
        self.container = self.client.get_database_client(settings.cosmos_database).get_container_client(
            settings.cosmos_container
        )

    def _read_item(self, item_id):
        try:
            return self.container.read_item(item_id, partition_key=self.club)
        except exceptions.CosmosResourceNotFoundError:
            return None

    def _control(self, allow_maintenance=False):
        control = self._read_item("club_state")
        if not control or control.get("schema_version") != SCHEMA_VERSION:
            raise StorageUnavailable("Cosmos club is not initialized or its schema is incompatible")
        if not allow_maintenance and control.get("mode") != "ready":
            raise StorageUnavailable("Club storage is in maintenance mode")
        return control

    def check_configuration(self):
        properties = self.container.read()
        if properties.get("partitionKey", {}).get("paths") != ["/club_id"]:
            raise StorageUnavailable("Cosmos container requires /club_id partitioning")
        unique = properties.get("uniqueKeyPolicy", {}).get("uniqueKeys", [])
        if {tuple(k["paths"]) for k in unique} != {("/identity_key",)}:
            raise StorageUnavailable("Cosmos container requires the identity_key unique policy")
        if self.client and not self.settings.cosmos_emulator:
            account = self.client.get_database_account()
            policy = account.ConsistencyPolicy or {}
            if policy.get("defaultConsistencyLevel") != "Strong" or len(account.WritableLocations) != 1:
                raise StorageUnavailable("Cosmos requires Strong consistency and a single write region")

    def health(self):
        try:
            self._control()
        except (
            exceptions.CosmosHttpResponseError,
            ServiceRequestError,
            ServiceResponseError,
            exceptions.CosmosClientTimeoutError,
        ) as exc:
            raise StorageUnavailable("Cosmos readiness check failed") from exc

    def _snapshot(self, *, allow_maintenance=False):
        for _ in range(self.settings.storage_retry_attempts):
            control = self._control(allow_maintenance=allow_maintenance)
            docs, size = {}, 0
            iterator = self.container.query_items(
                query="SELECT * FROM c WHERE c.club_id = @club AND c.kind NOT IN ('control', 'receipt')",
                parameters=[{"name": "@club", "value": self.club}],
                partition_key=self.club,
                max_item_count=100,
            )
            for item in iterator:  # Exhaust the SDK continuation pages; never return a partial roster.
                docs[item["id"]] = item
                size += len(encoded(item))
                if (
                    len(docs) > self.settings.cosmos_max_documents
                    or size > self.settings.cosmos_max_snapshot_bytes
                ):
                    raise StorageLimit("Club snapshot exceeds the configured supported size")
            if self._control(allow_maintenance=allow_maintenance)["_etag"] == control["_etag"]:
                return control, docs, decode(docs.values(), control["counters"])
        raise StorageConflict("Club changed during the read; please retry")

    def read(self, *, allow_maintenance=False):
        try:
            return self._snapshot(allow_maintenance=allow_maintenance)[2]
        except (
            exceptions.CosmosHttpResponseError,
            ServiceRequestError,
            ServiceResponseError,
            exceptions.CosmosClientTimeoutError,
        ) as exc:
            raise StorageUnavailable("Cosmos read failed") from exc

    def _charge(self, headers, _):
        logger.info("cosmos_batch request_charge=%s", headers.get("x-ms-request-charge", "unknown"))

    def execute(self, operation, *, command_id=None, fingerprint="", authorize=None):
        command_id = command_id or uuid4().hex
        receipt_id = f"receipt_{command_id}"
        for attempt in range(self.settings.storage_retry_attempts):
            try:
                control, original, state = self._snapshot()
                if authorize:
                    authorize(state)
                receipt = self._read_item(receipt_id)
                if receipt:
                    if receipt["data"]["fingerprint"] != fingerprint:
                        raise StorageConflict("Idempotency key was already used for another request")
                    return open_result(receipt["data"]["result"])
                result = jsonable_encoder(operation(state))
                state.validate()
                next_docs = encode(state, self.club)
                if (
                    len(next_docs) > self.settings.cosmos_max_documents
                    or sum(len(encoded(d)) for d in next_docs.values())
                    > self.settings.cosmos_max_snapshot_bytes
                ):
                    raise StorageLimit(
                        "This command would exceed the configured club storage limit; no changes were written"
                    )
                updated = {k: v for k, v in control.items() if not k.startswith("_")}
                updated["counters"] = state.counters
                updated["revision"] += 1
                operations = [("replace", ("club_state", updated), {"if_match_etag": control["_etag"]})]
                for item_id in original.keys() - next_docs.keys():
                    operations.append(("delete", (item_id,), {"if_match_etag": original[item_id]["_etag"]}))
                for item_id, doc in next_docs.items():
                    old = original.get(item_id)
                    if old is None:
                        operations.append(("create", (doc,)))
                    elif doc != {k: v for k, v in old.items() if not k.startswith("_")}:
                        operations.append(("replace", (item_id, doc), {"if_match_etag": old["_etag"]}))
                receipt = document(
                    self.club, "receipt", receipt_id, {"fingerprint": fingerprint, "result": seal(result)}
                )
                operations.append(("create", (receipt,)))
                preflight(operations)
                self.container.execute_item_batch(
                    operations, partition_key=self.club, retry_write=0, response_hook=self._charge
                )
                return result
            except (exceptions.CosmosHttpResponseError, exceptions.CosmosBatchOperationError) as exc:
                status = getattr(exc, "status_code", None)
                if status not in (408, 409, 412, 424, 429, 449, 500, 502, 503, 504):
                    raise StorageUnavailable(
                        "Cosmos command failed; check account access and configuration"
                    ) from exc
                delay = min(
                    float((getattr(exc, "headers", {}) or {}).get("x-ms-retry-after-ms", 100)) / 1000, 2
                )
            except (ServiceRequestError, ServiceResponseError, exceptions.CosmosClientTimeoutError):
                delay = 0.1
            if attempt + 1 < self.settings.storage_retry_attempts:
                time.sleep(delay)
        # No blind replay after an ambiguous commit: the same key must be retained by the caller.
        try:
            state = self.read()
            if authorize:
                authorize(state)
            receipt = self._read_item(receipt_id)
            if receipt and receipt["data"]["fingerprint"] == fingerprint:
                return open_result(receipt["data"]["result"])
        except (
            exceptions.CosmosHttpResponseError,
            ServiceRequestError,
            ServiceResponseError,
            exceptions.CosmosClientTimeoutError,
        ):
            pass
        raise StorageUnavailable("Cosmos command could not be confirmed; retry with the same idempotency key")

    def close(self):
        if self.client:
            self.client.close()
        if self.credential:
            self.credential.close()
