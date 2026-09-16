import pytest
from decimal import Decimal

from app.services.client_validation_service import ClientValidationService
from app.services.client_compare_service import ClientComparisonService


def test_required_client_fields_validation():
    record = {
        "client_id": "CLI001",
        "client_name": "Acme",
        "category": "IT Services",
        "contract_value": 100000,
        "revenue": 200000,
        "frequency": "Monthly",
        "bank_name": "HDFC",
        "account_holder_name": "Test User",
        "account_number": "1234567890",
        "ifsc_code": "HDFC0001234",
    }
    result = ClientValidationService.validate_record(record)
    assert result["valid"] is True
    assert result["errors"] == []


def test_missing_required_client_id_rejected():
    record = {
        "client_name": "Acme",
        "category": "IT Services",
        "contract_value": 100000,
        "revenue": 200000,
        "frequency": "Monthly",
        "bank_name": "HDFC",
        "account_holder_name": "Test User",
        "account_number": "1234567890",
        "ifsc_code": "HDFC0001234",
    }
    result = ClientValidationService.validate_record(record)
    assert result["valid"] is False
    assert any(err["field"] == "client_id" for err in result["errors"])


def test_duplicate_key_same_client_and_category_is_skipped():
    existing = {
        "client_id": "CLI001",
        "category": "IT Services",
        "client_name": "Acme",
        "contract_value": 100000,
        "revenue": 500000,
        "frequency": "Monthly",
        "bank_name": "HDFC",
        "account_holder_name": "Test User",
        "account_number": "1234567890",
        "ifsc_code": "HDFC0001234",
    }
    incoming = {**existing}
    status = ClientComparisonService.compare_record(existing, incoming)
    assert status["action"] == "SKIP"
    assert status["changed_fields"] == []


def test_changed_client_revenue_is_update():
    existing = {
        "client_id": "CLI001",
        "category": "IT Services",
        "client_name": "Acme",
        "contract_value": 100000,
        "revenue": 500000,
        "frequency": "Monthly",
        "bank_name": "HDFC",
        "account_holder_name": "Test User",
        "account_number": "1234567890",
        "ifsc_code": "HDFC0001234",
    }
    incoming = {**existing, "revenue": 600000}
    status = ClientComparisonService.compare_record(existing, incoming)
    assert status["action"] == "UPDATE"
    assert "revenue" in status["changed_fields"]


def test_same_client_id_different_category_allowed():
    existing = {"client_id": "CLI001", "category": "IT Services"}
    incoming = {"client_id": "CLI001", "category": "Consulting"}
    assert ClientComparisonService.business_key(existing) != ClientComparisonService.business_key(incoming)


def test_contract_value_conflict_is_detected():
    existing = {"contract_value": 1000000}
    agreement = {"contract_value": Decimal("1200000")}
    conflict = ClientComparisonService.detect_conflict(existing, agreement)
    assert conflict["conflict"] is True
    assert conflict["field"] == "contract_value"


def test_no_version_field_in_model_schema():
    from app.db.models.client import ClientMaster
    assert not hasattr(ClientMaster, "version")
