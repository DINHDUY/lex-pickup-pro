import pytest
from pydantic import ValidationError

from app.config import Settings
from app.storage.cosmos import CosmosStore
from app.storage.cosmos.manage import EMULATOR_KEY
from app.storage.interfaces import StorageUnavailable

from .fake_cosmos import MemoryContainer


@pytest.mark.parametrize(
    "values",
    [
        {"database_provider": "unknown"},
        {"database_provider": "cosmos"},
        {"database_provider": "cosmos", "cosmos_endpoint": "http://account.documents.azure.com"},
        {"cosmos_consistency_level": "Session"},
        {
            "database_provider": "cosmos",
            "cosmos_endpoint": "https://account.documents.azure.com",
            "cosmos_emulator": True,
            "cosmos_auth_mode": "emulator",
            "cosmos_key": EMULATOR_KEY,
        },
    ],
)
def test_invalid_provider_configuration_fails_closed(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_wrong_partition_and_missing_unique_policy_are_rejected():
    container = MemoryContainer()
    container.read = lambda: {"partitionKey": {"paths": ["/id"]}}
    store = CosmosStore(Settings(), container=container)
    with pytest.raises(StorageUnavailable, match="partitioning"):
        store.check_configuration()
    container.read = lambda: {"partitionKey": {"paths": ["/club_id"]}, "uniqueKeyPolicy": {"uniqueKeys": []}}
    with pytest.raises(StorageUnavailable, match="unique"):
        store.check_configuration()
