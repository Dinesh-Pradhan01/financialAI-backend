import uuid
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base, TimestampMixin

class UploadHistory(TimestampMixin, Base):
    __tablename__ = "upload_history"

    upload_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    total_records: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    success_records: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    failed_records: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    processing_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)

    validation_logs: Mapped[list["ValidationLogs"]] = relationship("ValidationLogs", back_populates="upload_history", cascade="all, delete-orphan")
    import_logs: Mapped[list["ImportLogs"]] = relationship("ImportLogs", back_populates="upload_history", cascade="all, delete-orphan")

class ValidationLogs(TimestampMixin, Base):
    __tablename__ = "validation_logs"

    upload_history_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("upload_history.id"), index=True, nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    invalid_value: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)

    upload_history: Mapped["UploadHistory"] = relationship("UploadHistory", back_populates="validation_logs")

class ImportLogs(TimestampMixin, Base):
    __tablename__ = "import_logs"

    upload_history_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("upload_history.id"), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    upload_history: Mapped["UploadHistory"] = relationship("UploadHistory", back_populates="import_logs")
