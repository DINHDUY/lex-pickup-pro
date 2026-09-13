from typing import Any, Callable, Protocol

from ..domain.club import ClubData


class StorageError(RuntimeError):
    pass


class StorageConflict(StorageError):
    pass


class StorageUnavailable(StorageError):
    pass


class StorageLimit(StorageError):
    pass


class Store(Protocol):
    def read(self) -> ClubData: ...
    def execute(
        self,
        operation: Callable[[ClubData], Any],
        *,
        command_id: str | None = None,
        fingerprint: str = "",
        authorize: Callable[[ClubData], None] | None = None,
    ) -> Any: ...
    def health(self) -> None: ...
    def close(self) -> None: ...
