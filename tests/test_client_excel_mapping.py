import pytest
from app.upload_engine.normalizers.client_normalizer import ClientNormalizer
from app.services.client_validation_service import ClientValidationService

def get_normalized(data: dict):
    norm = ClientNormalizer()
    res = norm.normalize([data])
    return res[0]

def test_underscore_headers():
    """Test 1 — Underscore headers"""
    data = {"client_id": "C-001", "client_name": "Acme"}
    normalized = get_normalized(data)
    assert normalized["client_id"] == "C-001"
    assert normalized["client_name"] == "Acme"

def test_space_headers():
    """Test 2 — Space headers"""
    data = {"CLIENT ID": "C-001", "CLIENT NAME": "Acme"}
    normalized = get_normalized(data)
    assert normalized["client_id"] == "C-001"
    assert normalized["client_name"] == "Acme"

def test_mixed_case():
    """Test 3 — Mixed case"""
    data = {"Client ID": "C-001", "Client Name": "Acme", "Status": "Active"}
    normalized = get_normalized(data)
    assert normalized["client_id"] == "C-001"
    assert normalized["client_name"] == "Acme"
    assert normalized["status"] == "Active"

def test_blank_optional_agreement_fields():
    """Test 4 — Blank optional agreement fields"""
    record = {
        "client_id": "C-001",
        "client_name": "Acme",
        "category": "Cat",
        "revenue": 100,
        "frequency": "Monthly",
        "contract_value": 100, # valid for now to test optional fields
        "contract_id": "",
        "contract_type": "",
        "contract_start_date": "",
        "contract_end_date": "",
        "currency": ""
    }
    res = ClientValidationService.validate_record(record, is_upload=True)
    assert res["valid"] is True
    assert len(res["errors"]) == 0

def test_blank_contract_value():
    """Test 5 & 6 — Blank contract value without agreement"""
    record = {
        "client_id": "C-001",
        "client_name": "Acme",
        "category": "Cat",
        "revenue": 100,
        "frequency": "Monthly",
        "contract_value": "", # blank
    }
    res = ClientValidationService.validate_record(record, is_upload=True)
    assert res["valid"] is False
    assert any(e["field"] == "contract_value" for e in res["errors"])

def test_status_string():
    """Test 7 — Status string"""
    data = {"Status": "ACTIVE"}
    normalized = get_normalized(data)
    assert isinstance(normalized["status"], str)
    assert normalized["status"] == "ACTIVE"

    data = {"Status": "pending"}
    normalized = get_normalized(data)
    assert isinstance(normalized["status"], str)
    assert normalized["status"] == "pending"

def test_unsupported_column():
    data = {"CLIENT ID": "C-001", "UnknownCol": "yes"}
    normalized = get_normalized(data)
    assert "UnknownCol" in normalized
    res = ClientValidationService.validate_record(normalized, is_upload=True)
    assert res["valid"] is False
    assert any(e["field"] == "UnknownCol" and e["error"] == "Unsupported Excel column" for e in res["errors"])
