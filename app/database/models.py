import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Numeric, Date, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="person", cascade="all, delete-orphan"
    )
    accounts: Mapped[List["Account"]] = relationship(
        "Account", back_populates="person", cascade="all, delete-orphan"
    )

class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="merchant")

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hash_md5: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="documents")
    account: Mapped[Optional["Account"]] = relationship(
        "Account", back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="document", cascade="all, delete-orphan"
    )
    metadata_logs: Mapped[Optional["ProcessingMetadata"]] = relationship(
        "ProcessingMetadata", back_populates="document", cascade="all, delete-orphan", uselist=False
    )

class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), default="savings", nullable=False)
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    opening_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0, nullable=False)
    closing_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0, nullable=False)
    statement_period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    statement_month: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="accounts")
    document: Mapped["Document"] = relationship("Document", back_populates="account")
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    merchant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True
    )
    transaction_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    value_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    debit_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0, nullable=False)
    credit_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0, nullable=False)
    running_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0, nullable=False)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utr_upi_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cheque_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="Uncategorized", nullable=False)
    classification: Mapped[str] = mapped_column(String(50), default="expense", nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # DEBIT or CREDIT
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="transactions")
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")
    merchant: Mapped[Optional["Merchant"]] = relationship("Merchant", back_populates="transactions")

class ProcessingMetadata(Base):
    __tablename__ = "processing_metadata"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    processing_time_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stages_completed: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped["Document"] = relationship("Document", back_populates="metadata_logs")
