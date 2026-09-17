import pytest
import uuid
import copy
from typing import Dict, Any

from app.services.agreement.schemas import VendorAgreementSchema, ClientAgreementSchema
from app.services.agreement.normalization_service import NormalizationService
from app.services.agreement.merge_service import MergeService

import sqlalchemy.orm.attributes
sqlalchemy.orm.attributes.flag_modified = lambda instance, key: None

class MockDB:
    class MockRecord:
        def __init__(self, upload_id: str, preview_data: list):
            self.id = uuid.UUID(upload_id)
            self.preview_data = preview_data

    class MockScalars:
        def __init__(self, records):
            self.records = records
        def first(self):
            return self.records[0] if self.records else None

    class MockResult:
        def __init__(self, scalars_obj):
            self.scalars_obj = scalars_obj
        def scalars(self):
            return self.scalars_obj

    def __init__(self):
        self.records = {}
        self.committed = False
    
    def add_history(self, upload_id: str, preview_data: list):
        self.records[upload_id] = self.MockRecord(upload_id, preview_data)
        
    async def execute(self, stmt):
        # mock finding upload_history by id
        return self.MockResult(self.MockScalars(list(self.records.values())))

    async def commit(self):
        self.committed = True


def test_schema_includes_contract_id():
    """TEST 1 — CONTRACT ID EXTRACTION Schema presence"""
    schema = VendorAgreementSchema.model_fields
    assert "contract_id" in schema, "Schema must include contract_id"
    assert schema["contract_id"].description is not None


def test_normalization_preserves_contract_id():
    """TEST 2 — FULL EXTRACTION normalization pass-through"""
    raw_data = {
        "contract_id": "CTR-V-101",
        "contract_type": "MSA",
        "contract_start_date": "2023-01-15",
        "contract_end_date": "2025-01-14",
        "contract_value": 150000.00,
        "currency": "INR"
    }
    
    normalized = NormalizationService.normalize_extracted_data(raw_data)
    
    assert normalized["contract_id"] == "CTR-V-101"
    assert normalized["contract_type"] == "MSA"
    assert normalized["contract_start_date"] == "2023-01-15"
    assert normalized["contract_end_date"] == "2025-01-14"
    assert normalized["contract_value"] == 150000.0
    assert normalized["currency"] == "INR"


import asyncio

def test_merge_into_existing_vendor_row():
    """TEST 3 & TEST 4 — MERGE INTO EXISTING VENDOR ROW & PRESERVE EXISTING DATA"""
    async def run_test():
        db = MockDB()
        upload_id = str(uuid.uuid4())
        
        existing_row = {
            "rowId": "row-3",
            "vendor_id": "V-001",
            "vendor_name": "TechNova Solutions",
            "category": "IT",
            "industry": "Technology",
            "bank_name": "HDFC",
            "contract_id": None,
            "contract_type": None,
            "contract_start_date": None,
            "contract_end_date": None,
            "contract_value": None,
            "currency": None
        }
        
        db.add_history(upload_id, [existing_row])
        
        extracted_data = {
            "contract_id": "CTR-V-101",
            "contract_value": 150000.0,
            "currency": "INR",
            "contract_type": "MSA",
            "contract_start_date": "2023-01-15",
            "contract_end_date": "2025-01-14",
            "valid": True
        }
        
        updated_row = await MergeService.merge_extraction_to_preview_row(
            upload_id=upload_id,
            preview_row_id="row-3",
            extracted_data=extracted_data,
            db=db
        )
        
        # Contract Fields merged
        assert updated_row["contract_id"] == "CTR-V-101"
        assert updated_row["contract_value"] == 150000.0
        assert updated_row["contract_type"] == "MSA"
        
        # Existing fields preserved
        assert updated_row["vendor_id"] == "V-001"
        assert updated_row["vendor_name"] == "TechNova Solutions"
        assert updated_row["category"] == "IT"
        assert updated_row["industry"] == "Technology"
        assert updated_row["bank_name"] == "HDFC"
    
    asyncio.run(run_test())


def test_multiple_vendors_association():
    """TEST 5 — MULTIPLE VENDORS"""
    async def run_test():
        db = MockDB()
        upload_id = str(uuid.uuid4())
        
        rows = [
            {"rowId": "row-1", "vendor_id": "V-A", "contract_id": None},
            {"rowId": "row-2", "vendor_id": "V-B", "contract_id": None}
        ]
        
        db.add_history(upload_id, rows)
        
        # Apply to V-A
        await MergeService.merge_extraction_to_preview_row(
            upload_id=upload_id,
            preview_row_id="row-1",
            extracted_data={"contract_id": "CTR-V-101", "valid": True},
            db=db
        )
        
        history_record = db.records[upload_id]
        
        assert history_record.preview_data[0]["contract_id"] == "CTR-V-101"
        assert history_record.preview_data[0]["vendor_id"] == "V-A"
        
        assert history_record.preview_data[1]["contract_id"] is None
        assert history_record.preview_data[1]["vendor_id"] == "V-B"
    
    asyncio.run(run_test())


def test_missing_contract_id():
    """TEST 6 — MISSING CONTRACT ID"""
    async def run_test():
        db = MockDB()
        upload_id = str(uuid.uuid4())
        
        rows = [
            {"rowId": "row-1", "vendor_id": "V-A", "contract_id": None},
        ]
        
        db.add_history(upload_id, rows)
        
        await MergeService.merge_extraction_to_preview_row(
            upload_id=upload_id,
            preview_row_id="row-1",
            extracted_data={"contract_type": "MSA", "valid": True}, # Missing contract_id
            db=db
        )
        
        history_record = db.records[upload_id]
        assert history_record.preview_data[0]["contract_id"] is None

    asyncio.run(run_test())
