from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Numeric, Date, DateTime, JSON, func, Boolean, UniqueConstraint

if TYPE_CHECKING:
    from app.business.models import GeneralInfo
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    """Mixin that adds created_at and updated_at columns with timezone to models."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Merchant
# ---------------------------------------------------------------------------

class Merchant(TimestampMixin, Base):
    """
    Canonical merchant entity — enriched with business context.
    A merchant can be global (business_id=NULL) or scoped to an SME.
    """
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    canonical_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), default="India", nullable=True)

    # Relationships
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="merchant")


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document(TimestampMixin, Base):
    """
    Represents an uploaded bank statement PDF linked to an SME business
    and optionally to a resolved persistent Account.
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hash_md5: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    document_type: Mapped[str] = mapped_column(String(50), default="BANK_STATEMENT", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    business: Mapped[Optional[GeneralInfo]] = relationship("GeneralInfo")
    account: Mapped[Optional["Account"]] = relationship("Account", back_populates="documents")
    bank_statement_data: Mapped[Optional["BankStatementData"]] = relationship(
        "BankStatementData", back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="document", cascade="all, delete-orphan"
    )
    metadata_logs: Mapped[Optional["ProcessingMetadata"]] = relationship(
        "ProcessingMetadata", back_populates="document", cascade="all, delete-orphan", uselist=False
    )


# ---------------------------------------------------------------------------
# Account (Persistent — one per real bank account per SME)
# ---------------------------------------------------------------------------

class Account(TimestampMixin, Base):
    """
    Persistent bank account entity. Deduplicated by (business_id, account_number, bank_name).
    Statement-specific data (balances, period) lives in BankStatementData.
    """
    __tablename__ = "accounts"

    __table_args__ = (
        UniqueConstraint("business_id", "account_number", "bank_name", name="uq_account_business_number_bank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=True
    )
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_holder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String(50), default="savings", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    business: Mapped[Optional[GeneralInfo]] = relationship("GeneralInfo")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="account")
    bank_statement_data: Mapped[List["BankStatementData"]] = relationship(
        "BankStatementData", back_populates="account"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# BankStatementData (per-document statement metadata)
# ---------------------------------------------------------------------------

class BankStatementData(Base):
    """
    Statement-specific metadata decoupled from the persistent Account.
    One row per uploaded document — captures opening/closing balances and period.
    """
    __tablename__ = "bank_statement_data"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    opening_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0, nullable=False)
    closing_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0.0, nullable=False)
    statement_period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    statement_month: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="bank_statement_data")
    account: Mapped[Optional["Account"]] = relationship("Account", back_populates="bank_statement_data")


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

class Transaction(Base):
    """
    Raw factual transaction record — "what happened".
    Connected to an SME business, a persistent account, and a document source.
    """
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    merchant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("transaction_categories.id", ondelete="SET NULL"), nullable=True
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
    raw_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    classification: Mapped[str] = mapped_column(String(50), default="expense", nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # DEBIT or CREDIT
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="transactions")
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")
    merchant: Mapped[Optional["Merchant"]] = relationship("Merchant", back_populates="transactions")


# ---------------------------------------------------------------------------
# Categorization — Intelligence Layer
# ---------------------------------------------------------------------------

class IntelligenceGroup(TimestampMixin, Base):
    """
    Top-level grouping for transaction categories.
    E.g. "Operating Expenses", "Revenue & Income", "Investments".
    """
    __tablename__ = "intelligence_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    categories: Mapped[List["TransactionCategory"]] = relationship(
        "TransactionCategory", back_populates="intelligence_group", cascade="all, delete-orphan"
    )


class TransactionCategory(TimestampMixin, Base):
    """
    A specific transaction category within an intelligence group.
    E.g. "Fuel" under "Operating Expenses".
    """
    __tablename__ = "transaction_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intelligence_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("intelligence_groups.id", ondelete="CASCADE"), nullable=False
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system_defined: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    intelligence_group: Mapped["IntelligenceGroup"] = relationship(
        "IntelligenceGroup", back_populates="categories"
    )
    rules: Mapped[List["CategoryRule"]] = relationship(
        "CategoryRule", back_populates="category", cascade="all, delete-orphan"
    )


class CategoryRule(Base):
    """
    Rule for auto-categorizing transactions into a TransactionCategory.
    Supports keyword matching, regex, or ML model-based classification.
    """
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transaction_categories.id", ondelete="CASCADE"), nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # KEYWORD_MATCH, REGEX, AI_MODEL
    match_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    category: Mapped["TransactionCategory"] = relationship("TransactionCategory", back_populates="rules")


# ---------------------------------------------------------------------------
# Processing Metadata
# ---------------------------------------------------------------------------

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
