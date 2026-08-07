import uuid
import logging
from typing import Any, Dict, List, Optional, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database.models import Base, Document, Account, Transaction, ProcessingMetadata, Merchant

logger = logging.getLogger(__name__)

# Dictionary mapping collection names (strings) to SQLAlchemy model classes
MODEL_MAPPING: Dict[str, Type[Base]] = {
    "documents": Document,
    "accounts": Account,
    "transactions": Transaction,
    "processing_metadata": ProcessingMetadata,
    "merchants": Merchant
}

class BaseRepository:
    def __init__(self, session: AsyncSession, model_or_name: Any):
        """
        Base repository pattern class to handle basic CRUD operations asynchronously on PostgreSQL.
        Supports both SQLAlchemy Model classes and string table names for backwards compatibility.
        """
        self.session = session
        if isinstance(model_or_name, str):
            if model_or_name not in MODEL_MAPPING:
                raise ValueError(f"Unknown table name mapping: {model_or_name}")
            self.model_class = MODEL_MAPPING[model_or_name]
        else:
            self.model_class = model_or_name

    async def get_by_id(self, id: str) -> Optional[Any]:
        """Fetch a single record by its string or UUID representation."""
        try:
            uuid_id = uuid.UUID(id) if isinstance(id, str) else id
        except ValueError:
            logger.warning(f"Invalid UUID string provided: {id}")
            return None
        return await self.session.get(self.model_class, uuid_id)

    async def find(self, query: Dict[str, Any], limit: int = 100, skip: int = 0) -> List[Any]:
        """Query multiple records matching the criteria dictionary."""
        stmt = select(self.model_class)
        for key, value in query.items():
            # If search field is _id, map to id
            search_key = "id" if key == "_id" else key
            attr = getattr(self.model_class, search_key, None)
            if attr is not None:
                # Convert foreign keys or ID strings to UUIDs
                if search_key in ("id", "document_id", "account_id") and isinstance(value, str):
                    try:
                        value = uuid.UUID(value)
                    except ValueError:
                        pass
                stmt = stmt.filter(attr == value)
                
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: Dict[str, Any]) -> str:
        """Insert a new record and return its UUID string representation."""
        # Convert _id key to id if present
        if "_id" in data:
            data["id"] = data.pop("_id")
            
        cleaned_data = {}
        for key, val in data.items():
            if key in ("id", "document_id", "account_id") and isinstance(val, str):
                try:
                    val = uuid.UUID(val)
                except ValueError:
                    pass
            cleaned_data[key] = val
            
        instance = self.model_class(**cleaned_data)
        self.session.add(instance)
        await self.session.flush()  # Flushes to db to populate primary key UUIDs
        return str(instance.id)

    async def update(self, id: str, data: Dict[str, Any]) -> bool:
        """Update an existing record by its UUID. Returns True if updated, else False."""
        instance = await self.get_by_id(id)
        if not instance:
            return False
            
        for key, val in data.items():
            if key in ("id", "_id"):
                continue  # Prevent primary key alterations
            if key in ("document_id", "account_id") and isinstance(val, str):
                try:
                    val = uuid.UUID(val)
                except ValueError:
                    pass
            setattr(instance, key, val)
            
        await self.session.flush()
        return True

    async def delete(self, id: str) -> bool:
        """Delete a record by its UUID. Returns True if deleted, else False."""
        instance = await self.get_by_id(id)
        if not instance:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

