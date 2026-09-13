from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from ..config import get_settings
from .interfaces import Store


@lru_cache
def get_store():
    settings = get_settings()
    if settings.database_provider == "cosmos":
        from .cosmos import CosmosStore

        return CosmosStore(settings)
    from ..db import SessionLocal
    from .sql import SqlStore

    return SqlStore(SessionLocal)


def get_data(request: Request, store: Annotated[Store, Depends(get_store)]):
    data = store.read()
    data.store, data.request = store, request
    return data
