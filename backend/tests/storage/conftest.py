import os
from uuid import uuid4

import pytest
from azure.cosmos import PartitionKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base
from app.main import app
from app.security import _attempts
from app.storage.cosmos import CosmosStore
from app.storage.cosmos.manage import EMULATOR_KEY, initialize
from app.storage.factory import get_store
from app.storage.sql import SqlStore

from .fake_cosmos import MemoryContainer

PROVIDERS = ["sql", "cosmos-double"]
if os.environ.get("LEX_TEST_COSMOS_ENDPOINT"):
    PROVIDERS.append("cosmos-sdk")


@pytest.fixture(params=PROVIDERS)
def store(request, session_factory, tmp_path):
    initial = SqlStore(session_factory).read()
    if request.param == "sql":
        engine = create_engine(f"sqlite:///{tmp_path}/contract.db", connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
        result = SqlStore(sessionmaker(engine, expire_on_commit=False))
    else:
        endpoint = os.environ.get("LEX_TEST_COSMOS_ENDPOINT", "http://localhost:18081")
        emulator = endpoint.startswith("http://localhost:") or endpoint.startswith("http://127.0.0.1:")
        database = os.environ.get("LEX_TEST_COSMOS_DATABASE", "lex_test_cosmos")
        if not database.startswith("lex_test_"):
            raise RuntimeError("Cosmos integration requires a disposable lex_test_* database")
        settings = Settings(
            database_provider="cosmos",
            cosmos_endpoint=endpoint,
            cosmos_auth_mode="emulator" if emulator else "default_credential",
            cosmos_key=EMULATOR_KEY if emulator else "",
            cosmos_emulator=emulator,
            cosmos_database=database,
            cosmos_container=os.environ.get("LEX_TEST_COSMOS_CONTAINER", "club_data"),
            cosmos_club_id="test-" + uuid4().hex,
        )
        result = (
            CosmosStore(settings, container=MemoryContainer())
            if request.param == "cosmos-double"
            else CosmosStore(settings)
        )
        if request.param == "cosmos-sdk" and emulator:
            database_client = result.client.create_database_if_not_exists(database)
            result.container = database_client.create_container_if_not_exists(
                settings.cosmos_container,
                partition_key=PartitionKey(path="/club_id"),
                unique_key_policy={"uniqueKeys": [{"paths": ["/identity_key"]}]},
            )
        initialize(result)

    def seed(data):
        data.tables = initial.clone().tables
        data.counters = initial.counters.copy()

    result.execute(seed)
    yield result
    if request.param == "cosmos-sdk":
        for doc in list(
            result.container.query_items(
                query="SELECT * FROM c WHERE c.club_id = @club",
                parameters=[{"name": "@club", "value": result.club}],
                partition_key=result.club,
            )
        ):
            result.container.delete_item(doc["id"], partition_key=result.club)
    result.close()
    if request.param == "sql":
        engine.dispose()


@pytest.fixture
def api(store):
    app.dependency_overrides[get_store] = lambda: store
    _attempts.clear()
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "admin@example.com", "password": "TestPassword2026!"}
            ).status_code
            == 200
        )
        yield client
    app.dependency_overrides.clear()
