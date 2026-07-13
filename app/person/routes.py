"""
Person profile API routes.
- GET   /api/persons/me  - Get profile of the current logged-in user
- PATCH /api/persons/me  - Update profile of the current logged-in user
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.dependencies import get_current_session_user
from app.auth.model import User
from app.database.connection import get_db
from app.database.models import Person

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persons", tags=["persons"])

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class PersonResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    pan_number: Optional[str] = None
    occupation: Optional[str] = None
    bank_count: Optional[int] = None
    primary_bank: Optional[str] = None
    profile_completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PersonUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    pan_number: Optional[str] = None
    occupation: Optional[str] = None
    bank_count: Optional[int] = None
    primary_bank: Optional[str] = None

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/me", response_model=PersonResponse, summary="Get current user's person profile")
async def get_my_profile(
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.person_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No person profile associated with this user."
        )

    stmt = select(Person).where(Person.id == current_user.person_id)
    result = await db.execute(stmt)
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person profile not found."
        )

    return person


@router.patch("/me", response_model=PersonResponse, summary="Update current user's person profile")
async def update_my_profile(
    payload: PersonUpdateRequest,
    current_user: User = Depends(get_current_session_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info("PATCH /persons/me called for user %s (person_id: %s) with payload: %s", 
                current_user.id, current_user.person_id, payload.model_dump(exclude_unset=True))
                
    if not current_user.person_id:
        logger.error("PATCH /persons/me failed: No person profile associated with user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No person profile associated with this user."
        )

    stmt = select(Person).where(Person.id == current_user.person_id)
    result = await db.execute(stmt)
    person = result.scalar_one_or_none()

    if not person:
        logger.error("PATCH /persons/me failed: Person profile not found for ID %s (user: %s)", 
                     current_user.person_id, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person profile not found."
        )

    # Update fields that were provided (not None)
    update_data = payload.model_dump(exclude_unset=True)

    # The DB column date_of_birth is TIMESTAMP WITHOUT TIME ZONE (naive).
    # The frontend sends an ISO string with TZ offset (e.g. "2000-01-01T00:00:00Z"),
    # which Pydantic parses as timezone-aware. Strip tzinfo so asyncpg doesn't choke.
    if "date_of_birth" in update_data and update_data["date_of_birth"] is not None:
        dob = update_data["date_of_birth"]
        if hasattr(dob, "tzinfo") and dob.tzinfo is not None:
            update_data["date_of_birth"] = dob.replace(tzinfo=None)

    for key, value in update_data.items():
        setattr(person, key, value)

    # Mark profile completed
    person.profile_completed = True

    await db.flush()
    logger.info("Updated person profile %s for user %s. profile_completed set to True.", person.id, current_user.id)

    return person
