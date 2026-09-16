from datetime import datetime, timezone
from sqlalchemy import String, Numeric, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class ClientMaster(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("client_id", "category", name="uq_client_id_category"),
    )

    client_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    client_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)

    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_id: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    contract_end_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    contract_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    revenue: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    payment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    frequency: Mapped[str] = mapped_column(String, nullable=False)
    recurring: Mapped[str | None] = mapped_column(String, nullable=True)
    bank_name: Mapped[str] = mapped_column(String, nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String, nullable=False)
    account_number: Mapped[str] = mapped_column(String, nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)

    agreement_document_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agreement_file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    agreement_extraction_confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    upload_id: Mapped[str | None] = mapped_column(String, nullable=True)
