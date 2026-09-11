import uuid
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, JSON, Date, Numeric, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base, TimestampMixin

class AgreementDocument(TimestampMixin, Base):
    __tablename__ = "agreement_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    preview_row_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, index=True, nullable=False) # 'client' or 'vendor'
    upload_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Status: NOT_UPLOADED, UPLOADED, PROCESSING, EXTRACTED, NEEDS_REVIEW, FAILED
    status: Mapped[str] = mapped_column(String, default="UPLOADED", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    extractions: Mapped[list["AgreementExtractionResult"]] = relationship(
        "AgreementExtractionResult", back_populates="document", cascade="all, delete-orphan"
    )

class AgreementExtractionResult(TimestampMixin, Base):
    __tablename__ = "agreement_extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), index=True, nullable=False)
    preview_row_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    contract_id: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_value: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)

    field_confidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_extraction_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    document: Mapped["AgreementDocument"] = relationship("AgreementDocument", back_populates="extractions")
