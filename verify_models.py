"""Quick verification that all SpotLite V2 models import correctly."""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.models import (
    Base, Merchant, Document, Account, Transaction, ProcessingMetadata,
    BankStatementData, IntelligenceGroup, TransactionCategory, CategoryRule
)
from app.risk.models import RiskRule, RiskDetection, RiskDetectionTransaction

print("All models imported successfully!")
tables = sorted(Base.metadata.tables.keys())
print(f"\nRegistered tables ({len(tables)}):")
for t in tables:
    print(f"  - {t}")
