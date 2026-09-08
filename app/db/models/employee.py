from sqlalchemy import String, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, SoftDeleteMixin

class EmployeeMaster(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "employee_master"

    employee_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    employee_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, index=True, nullable=False)
    joining_date: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, nullable=False)
    designation: Mapped[str] = mapped_column(String, nullable=False)
    salary: Mapped[str] = mapped_column(String, nullable=False)
    account_number: Mapped[str] = mapped_column(String, nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String, nullable=False)
    bank_name: Mapped[str] = mapped_column(String, nullable=False)

    employment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_frequency: Mapped[str | None] = mapped_column(String, nullable=True)
    account_holder_name: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(String, nullable=True)
