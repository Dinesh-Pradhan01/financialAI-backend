from typing import Annotated, Any
from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

def validate_object_id(v: Any) -> str:
    """Validate and convert an incoming value to a valid MongoDB ObjectId string."""
    if isinstance(v, ObjectId):
        return str(v)
    if not isinstance(v, str) or not ObjectId.is_valid(v):
        raise ValueError(f"Invalid ObjectId: {v}")
    return v

# Annotated type helper for MongoDB ObjectId mapping
PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]

class MongoBaseModel(BaseModel):
    """
    Base model for MongoDB documents incorporating ObjectId mapping.
    Maps '_id' from MongoDB to 'id' in application code.
    """
    id: PyObjectId = Field(default=None, alias="_id")

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )
