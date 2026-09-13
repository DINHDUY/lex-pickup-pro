"""Explicit Cosmos provisioning (emulator only), initialization and schema compatibility checks."""

import argparse
import json

from azure.cosmos import PartitionKey, exceptions

from ...config import get_settings
from ..interfaces import StorageError, StorageUnavailable
from . import CosmosStore
from .documents import SCHEMA_VERSION, document

# This emulator credential is public; Azure account keys are deliberately unsupported.
EMULATOR_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHlmDFeNp3v1xWkB7WqRE2p5CGVQ9pq5Pxl2myitc1oCZ4u6HVh5SZbQ=="


def initialize(store):
    store.check_configuration()
    control = document(store.club, "control", "club_state", {})
    control.update(counters={}, revision=0, mode="ready")
    try:
        store.container.create_item(control)
    except exceptions.CosmosResourceExistsError:
        store._control(allow_maintenance=True)


def check(store):
    store.check_configuration()
    state = store.read()  # Validates every document and reference, not just the control version.
    return {"schema_version": SCHEMA_VERSION, "counts": {k: len(v) for k, v in state.tables.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["provision-emulator", "init", "check", "upgrade"])
    args = parser.parse_args()
    settings = get_settings()
    if settings.database_provider != "cosmos":
        parser.error("Select DATABASE_PROVIDER=cosmos")
    store = CosmosStore(settings)
    try:
        if args.action == "provision-emulator":
            if not settings.cosmos_emulator or settings.app_env == "production":
                raise StorageUnavailable("Use the Bicep deployment for Azure resources")
            database = store.client.create_database_if_not_exists(settings.cosmos_database)
            store.container = database.create_container_if_not_exists(
                settings.cosmos_container,
                partition_key=PartitionKey(path="/club_id"),
                unique_key_policy={"uniqueKeys": [{"paths": ["/identity_key"]}]},
            )
            initialize(store)
        elif args.action == "init":
            initialize(store)
        # Version 1 is the first format. Never guess how to rewrite unknown document versions.
        # Future upgrades belong here as explicit resumable transforms while maintenance is set.
        print(json.dumps(check(store)))
    except (StorageError, exceptions.CosmosHttpResponseError) as exc:
        parser.exit(
            2,
            f"Cosmos {args.action} failed ({type(exc).__name__}). Check configuration, access and schema.\n",
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
