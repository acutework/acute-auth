"""Where the picker option lists come from."""

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog.data import CATALOGS, CatalogKind
from app.models.onboarding import CatalogItemRow


class CatalogRepository(ABC):
    @abstractmethod
    async def list_items(self, kind: CatalogKind) -> list[str]: ...

    async def list_all(self) -> dict[str, list[str]]:
        return {kind.value: await self.list_items(kind) for kind in CatalogKind}


class StaticCatalogRepository(CatalogRepository):
    """Returns the seed lists directly. Used when there is no database."""

    async def list_items(self, kind: CatalogKind) -> list[str]:
        return list(CATALOGS.get(kind, []))


class PostgresCatalogRepository(CatalogRepository):
    """Reads catalog_items, so a specialty can be added without an app release."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def list_items(self, kind: CatalogKind) -> list[str]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(CatalogItemRow.label)
                .where(
                    CatalogItemRow.kind == kind.value,
                    CatalogItemRow.is_active.is_(True),
                )
                .order_by(CatalogItemRow.sort_order, CatalogItemRow.label)
            )
            labels = list(rows)
        # An unseeded database should not leave the app with empty pickers.
        return labels or list(CATALOGS.get(kind, []))
