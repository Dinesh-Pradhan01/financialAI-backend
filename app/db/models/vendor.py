from datetime import date, datetime, timezone
from sqlalchemy import String, Boolean, Date, Numeric, Text, UniqueConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, SoftDeleteMixin

class VendorMaster(SoftDeleteMixin, Base):
    __tablename__ = "vendor_master"
    __table_args__ = (
        UniqueConstraint("business_id", "vendor_id", "category", name="uq_business_vendor_id_category"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    vendor_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    category: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)

    vendor_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    contract_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)  # OPTIONAL
    contract_value: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    monthly_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    frequency: Mapped[str] = mapped_column(String, nullable=False)
    bank_name: Mapped[str] = mapped_column(String, nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String, nullable=False)
    account_number: Mapped[str] = mapped_column(String, index=True, nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String, index=True, nullable=False)

    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    recurring: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[str | None] = mapped_column(String, nullable=True, default="system")
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True, default="system")

