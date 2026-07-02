from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

class BaseRepository:
    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        """
        Base repository pattern class to handle basic CRUD operations asynchronously on MongoDB.
        """
        self.db = db
        self.collection = db[collection_name]

    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single document by its string representation of ObjectId."""
        if not ObjectId.is_valid(id):
            return None
        return await self.collection.find_one({"_id": ObjectId(id)})

    async def find(self, query: Dict[str, Any], limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """Query multiple documents from the collection."""
        cursor = self.collection.find(query).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def create(self, data: Dict[str, Any]) -> str:
        """Insert a new document and return the string representation of its inserted ID."""
        if "_id" in data and isinstance(data["_id"], str) and ObjectId.is_valid(data["_id"]):
            data["_id"] = ObjectId(data["_id"])
            
        result = await self.collection.insert_one(data)
        return str(result.inserted_id)

    async def update(self, id: str, data: Dict[str, Any]) -> bool:
        """Update an existing document by its ID. Returns True if modified, else False."""
        if not ObjectId.is_valid(id):
            return False
        
        # Prevent modification of the primary key
        if "_id" in data:
            del data["_id"]
            
        result = await self.collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": data}
        )
        return result.modified_count > 0

    async def delete(self, id: str) -> bool:
        """Delete a document by its ID. Returns True if deleted, else False."""
        if not ObjectId.is_valid(id):
            return False
            
        result = await self.collection.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0
