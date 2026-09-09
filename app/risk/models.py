"""
Risk Schema Models — SpotLite Transaction Risk Schema V2

Implements Section 5 of the SpotLite_Transaction_Risk_Schema_Final.pdf:
- RiskRule: configurable risk detection rules (global or per-business)
- RiskDetection: detected risk incidents with scoring and review workflow
- RiskDetectionTransaction: junction table linking detections to evidence transactions
"""

from __future__ import annotations
import uuid
from datetime import datetime, date
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import (
    String, Integer, Float, Text, ForeignKey, Date, DateTime, Boolean, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models import Base, TimestampMixin

if TYPE_CHECKING:
    from app.business.models import GeneralInfo
    from app.database.models import Account, Merchant, Transaction


class RiskRule(TimestampMixin, Base):
    """
    Configurable risk detection rule.
    Global rules have business_id=NULL; per-SME rules have business_id set.
    """
    __tablename__ = "risk_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=True
    )

    rule_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # TRANSACTION, VELOCITY, PATTERN, COMPLIANCE
    severity: Mapped[str] = mapped_column(
        String(20), default="MEDIUM", nullable=False
    )  # LOW, MEDIUM, HIGH, CRITICAL
    rule_definition: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    threshold_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_system_defined: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    detections: Mapped[List["RiskDetection"]] = relationship(
        "RiskDetection", back_populates="risk_rule", cascade="all, delete-orphan"
    )


class RiskDetection(TimestampMixin, Base):
    """
    A detected risk incident — scored, reviewable, and linked to evidence transactions.
    """
    __tablename__ = "risk_detections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("general_info.id", ondelete="CASCADE"), nullable=False
    )
    risk_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_rules.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    merchant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("transaction_categories.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0-100
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 0-1.0

    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Review workflow
    status: Mapped[str] = mapped_column(
        String(30), default="OPEN", nullable=False
    )  # OPEN, REVIEWED, DISMISSED, ESCALATED
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    risk_rule: Mapped["RiskRule"] = relationship("RiskRule", back_populates="detections")
    evidence_transactions: Mapped[List["RiskDetectionTransaction"]] = relationship(
        "RiskDetectionTransaction", back_populates="risk_detection", cascade="all, delete-orphan"
    )


class RiskDetectionTransaction(Base):
    """
    Junction table linking a RiskDetection to one or more Transaction rows
    that serve as evidence for the detection.
    """
    __tablename__ = "risk_detection_transactions"

    risk_detection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_detections.id", ondelete="CASCADE"), primary_key=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Relationships
    risk_detection: Mapped["RiskDetection"] = relationship(
        "RiskDetection", back_populates="evidence_transactions"
    )
    transaction: Mapped["Transaction"] = relationship("Transaction")
