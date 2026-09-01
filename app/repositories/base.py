from typing import Generic, TypeVar, Type, Any, Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel
import uuid

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: uuid.UUID) -> Optional[ModelType]:
        query = select(self.model).where(self.model.id == id)
        if hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted == False)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_by_field(self, db: AsyncSession, field: str, value: Any) -> Optional[ModelType]:
        query = select(self.model).where(getattr(self.model, field) == value)
        if hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted == False)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[ModelType]:
        query = select(self.model).offset(skip).limit(limit)
        if hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted == False)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = obj_in.model_dump(exclude_unset=True)
        db_obj = self.model(**obj_in_data)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(self, db: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchemaType | Dict[str, Any]) -> ModelType:
        obj_data = db_obj.__dict__
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def soft_delete(self, db: AsyncSession, *, id: uuid.UUID) -> Optional[ModelType]:
        obj = await self.get(db=db, id=id)
        if obj:
            obj.is_deleted = True
            db.add(obj)
            await db.commit()
        return obj

    async def exists(self, db: AsyncSession, field: str, value: Any) -> bool:
        obj = await self.get_by_field(db, field, value)
        return obj is not None

    async def count(self, db: AsyncSession) -> int:
        query = select(func.count()).select_from(self.model).where(self.model.is_deleted == False)
        result = await db.execute(query)
        return result.scalar_one()

    async def bulk_insert(self, db: AsyncSession, objects: List[CreateSchemaType]) -> None:
        db_objects = [self.model(**obj.model_dump(exclude_unset=True)) for obj in objects]
        db.add_all(db_objects)
        await db.commit()

    async def bulk_update(self, db: AsyncSession, id_field: str, updates: List[Dict[str, Any]]) -> None:
        # Requires advanced handling in real systems depending on dialets, using a simple loop for generic safety
        for update_data in updates:
            ident = update_data.pop(id_field)
            stmt = update(self.model).where(getattr(self.model, id_field) == ident).values(**update_data)
            await db.execute(stmt)
        await db.commit()

    async def bulk_delete(self, db: AsyncSession, ids: List[uuid.UUID]) -> None:
        stmt = update(self.model).where(self.model.id.in_(ids)).values(is_deleted=True)
        await db.execute(stmt)
        await db.commit()
