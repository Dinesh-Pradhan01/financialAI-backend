from datetime import date
from sqlalchemy import String, Boolean, Date, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, SoftDeleteMixin

class VendorMaster(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "vendor_master"

    vendor_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    vendor_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    contract_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
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
