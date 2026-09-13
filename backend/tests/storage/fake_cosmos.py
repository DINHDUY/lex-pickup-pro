"""A deterministic transactional container double. The real SDK suite uses the same contract tests."""

from copy import deepcopy
from threading import RLock
from uuid import uuid4

from azure.cosmos import exceptions


class MemoryContainer:
    def __init__(self):
        self.items = {}
        self.lock = RLock()
        self.batch_count = 0
        self.pages = 0
        self.before_batch = None
        self.after_batch = None
        self.fail_status = None

    def read(self):
        return {
            "partitionKey": {"paths": ["/club_id"]},
            "uniqueKeyPolicy": {"uniqueKeys": [{"paths": ["/identity_key"]}]},
        }

    def read_item(self, item, *, partition_key, **kwargs):
        with self.lock:
            if (partition_key, item) not in self.items:
                raise exceptions.CosmosResourceNotFoundError(status_code=404)
            return deepcopy(self.items[partition_key, item])

    def create_item(self, body, **kwargs):
        with self.lock:
            identity = (body["club_id"], body["id"])
            if identity in self.items:
                raise exceptions.CosmosResourceExistsError(status_code=409)
            body = {**deepcopy(body), "_etag": uuid4().hex}
            self.items[identity] = body
            return deepcopy(body)

    def replace_item(self, item, body, *, etag=None, **kwargs):
        with self.lock:
            key = body["club_id"], item
            if etag and self.items[key]["_etag"] != etag:
                raise exceptions.CosmosAccessConditionFailedError(status_code=412)
            self.items[key] = {**deepcopy(body), "_etag": uuid4().hex}
            return deepcopy(self.items[key])

    def query_items(self, query, *, partition_key, max_item_count=100, **kwargs):
        with self.lock:
            rows = [deepcopy(d) for (club, _), d in self.items.items() if club == partition_key]
        if "NOT IN" in query:
            rows = [r for r in rows if r["kind"] not in ("control", "receipt")]
        elif "!= 'control'" in query:
            rows = [r for r in rows if r["kind"] != "control"]
        elif "= 'receipt'" in query:
            rows = [r for r in rows if r["kind"] == "receipt"]
        for index, row in enumerate(rows):
            if index % max_item_count == 0:
                self.pages += 1
            yield row

    def execute_item_batch(self, operations, *, partition_key, **kwargs):
        if self.before_batch:
            self.before_batch()
        with self.lock:
            self.batch_count += 1
            pending = deepcopy(self.items)
            for index, operation in enumerate(operations):
                kind, args = operation[:2]
                options = operation[2] if len(operation) > 2 else {}
                item_id = args[0]["id"] if kind == "create" else args[0]
                key = partition_key, item_id
                status = self.fail_status
                if kind == "create" and key in pending:
                    status = 409
                if (
                    options.get("if_match_etag")
                    and pending.get(key, {}).get("_etag") != options["if_match_etag"]
                ):
                    status = 412
                if status:
                    raise exceptions.CosmosBatchOperationError(index, {}, status, "Injected batch failure")
                if kind == "delete":
                    del pending[key]
                else:
                    pending[key] = {**deepcopy(args[-1]), "_etag": uuid4().hex}
            unique = [(club, d["identity_key"]) for (club, _), d in pending.items()]
            if len(unique) != len(set(unique)):
                raise exceptions.CosmosBatchOperationError(0, {}, 409, "Duplicate unique key")
            self.items = pending
        if self.after_batch:
            self.after_batch()
        return []
