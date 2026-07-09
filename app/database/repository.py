"""
Generic async repository pattern for SQLAlchemy ORM models.
"""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """
    Base repository providing common CRUD operations on a SQLAlchemy model.
    """

    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: int) -> Optional[T]:
        """Fetch a single record by primary key."""
        return await self.session.get(self.model, id)

    async def find(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[T]:
        """Query records with optional column-value filters."""
        stmt = select(self.model)
        if filters:
            for col, val in filters.items():
                stmt = stmt.where(getattr(self.model, col) == val)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj: T) -> T:
        """Insert a new record and return it with its generated ID."""
        self.session.add(obj)
        await self.session.flush()  # assigns the ID
        await self.session.refresh(obj)
        return obj

    async def update_by_id(self, id: int, data: Dict[str, Any]) -> bool:
        """Update a record by primary key. Returns True if a row was matched."""
        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .values(**data)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def delete_by_id(self, id: int) -> bool:
        """Delete a record by primary key. Returns True if a row was deleted."""
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0
