import uuid
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Date, DateTime, JSON, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models import Base, TimestampMixin

#0810PbMKD
class GeneralInfo(TimestampMixin, Base):
    """Step 1: Master legal profile for the business."""
    __tablename__ = "general_info"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_category: Mapped[str] = mapped_column(String(100), nullable=False)
    business_type: Mapped[str] = mapped_column(String(100), nullable=False)
    cin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    business_pan: Mapped[str] = mapped_column(String(10), nullable=False)
    udyam_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    date_of_incorporation: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    registered_address: Mapped[str] = mapped_column(Text, nullable=False)
    operational_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    pincode: Mapped[str] = mapped_column(String(20), nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    official_email: Mapped[str] = mapped_column(String(255), nullable=False)
    official_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    current_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    leadership_info: Mapped[Optional["LeadershipInfo"]] = relationship(
        "LeadershipInfo", back_populates="business", cascade="all, delete-orphan", uselist=False
    )
    financial_info: Mapped[Optional["FinancialInfo"]] = relationship(
        "FinancialInfo", back_populates="business", cascade="all, delete-orphan", uselist=False
    )
    verification: Mapped[Optional["BusinessVerification"]] = relationship(
        "BusinessVerification", back_populates="business", cascade="all, delete-orphan", uselist=False
    )
    documents: Mapped[List["BusinessVerificationDocument"]] = relationship(
        "BusinessVerificationDocument", back_populates="business", cascade="all, delete-orphan"
    )


class LeadershipInfo(TimestampMixin, Base):
    """Step 2: Business operational profile."""
    __tablename__ = "leadership_info"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    founder_ceo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    founder_ceo_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    founder_ceo_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    founder_ceo_designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    number_of_employees: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    number_of_branches: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    business_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    primary_product_service: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cfo_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cfo_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cfo_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cfo_designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    invite_cfo: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    
    hr_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hr_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hr_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    hr_designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    invite_hr: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)

    business: Mapped["GeneralInfo"] = relationship("GeneralInfo", back_populates="leadership_info")


class FinancialInfo(TimestampMixin, Base):
    """Step 3: Banking & financial setup details."""
    __tablename__ = "financial_info"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    primary_bank: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    number_of_accounts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    has_business_loan: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_business_credit_card: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    accounting_software: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    digital_payment_methods: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=True)

    business: Mapped["GeneralInfo"] = relationship("GeneralInfo", back_populates="financial_info")


class BusinessVerification(TimestampMixin, Base):
    """Step 4: Lightweight KYC verification status."""
    __tablename__ = "business_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    verification_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    business: Mapped["GeneralInfo"] = relationship("GeneralInfo", back_populates="verification")


class BusinessVerificationDocument(TimestampMixin, Base):
    """Uploaded verification documents."""
    __tablename__ = "business_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=False, index=True
    )

    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_category: Mapped[str] = mapped_column(String(50), default="mandatory", nullable=False) # mandatory, optional, recommended
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    upload_status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)

    business: Mapped["GeneralInfo"] = relationship("GeneralInfo", back_populates="documents")
