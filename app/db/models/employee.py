from sqlalchemy import String, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, SoftDeleteMixin

class EmployeeMaster(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "employee_master"

    employee_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    employee_name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[str | None] = mapped_column(String, nullable=True)
    joining_date: Mapped[str | None] = mapped_column(String, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    designation: Mapped[str | None] = mapped_column(String, nullable=True)
    manager: Mapped[str | None] = mapped_column(String, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    
    salary: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_salary: Mapped[str | None] = mapped_column(String, nullable=True)
    hike_percentage: Mapped[str | None] = mapped_column(String, nullable=True)
    salary_frequency: Mapped[str | None] = mapped_column(String, nullable=True)
    
    pan: Mapped[str | None] = mapped_column(String, nullable=True)
    aadhaar: Mapped[str | None] = mapped_column(String, nullable=True)
    
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    
    account_holder_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_number: Mapped[str | None] = mapped_column(String, nullable=True)
    confirm_account_number: Mapped[str | None] = mapped_column(String, nullable=True)
    ifsc_code: Mapped[str | None] = mapped_column(String, nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String, nullable=True)
    account_type: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(String, nullable=True)
