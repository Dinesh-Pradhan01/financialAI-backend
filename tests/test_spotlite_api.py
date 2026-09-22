"""
Test suite for Spotlite Executive Metrics Engine & LLM-Augmented Features API
"""

import sys
import os
from fastapi.testclient import TestClient

# Ensure app is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


def test_spotlite_tier1_metrics():
    """Verify GET /api/v1/spotlite/metrics/tier1 returns expected executive insights."""
    with TestClient(app) as client:
        response = client.get("/api/v1/spotlite/metrics/tier1")
        assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
        
        body = response.json()
        assert body["success"] is True
        data = body["data"]

        # Verify Tier 1 key metrics presence
        assert "room_above_break_even" in data
        assert "plausible_shock_runway" in data
        assert "concentration_risk_radar" in data
        assert "cost_structure_flexibility" in data
        assert "vendor_overbilling_detector" in data
        assert "idle_cash_forfeited_income" in data

        # Verify numerical assertions and insights
        be = data["room_above_break_even"]
        assert be["monthly_rupee_cushion"] > 0
        assert "cushion" in be["executive_insight"].lower()

        shock = data["plausible_shock_runway"]
        assert "Technova" in shock["churned_client_name"] or "Technova" in shock["executive_insight"]

        overbill = data["vendor_overbilling_detector"]
        assert overbill["monthly_overbill_amount"] == 85000.0
        assert overbill["annualized_recoverable_cash"] == 1020000.0

        idle = data["idle_cash_forfeited_income"]
        assert idle["idle_cash_surplus"] > 0
        assert idle["annualized_unearned_interest"] > 0


def test_spotlite_tier2_metrics():
    """Verify GET /api/v1/spotlite/metrics/tier2 returns expected contextual metrics."""
    with TestClient(app) as client:
        response = client.get("/api/v1/spotlite/metrics/tier2")
        assert response.status_code == 200
        
        body = response.json()
        assert body["success"] is True
        data = body["data"]

        assert "client_payment_drift" in data
        assert "workforce_ratios" in data
        assert "weekly_spend_cyclicality" in data
        assert "efficiency_ratios" in data

        assert data["workforce_ratios"]["headcount"] == 12
        assert "Saturday" in data["weekly_spend_cyclicality"]["day_of_week_breakdown"]


def test_spotlite_llm_augmented_insights():
    """Verify GET /api/v1/spotlite/augmented/insights returns LLM feature capabilities."""
    with TestClient(app) as client:
        response = client.get("/api/v1/spotlite/augmented/insights?use_ai=false")
        assert response.status_code == 200
        
        body = response.json()
        assert body["success"] is True
        data = body["data"]

        assert "stage0_classification_sample" in data
        assert "capability1_contract_semantic_reconciliation" in data
        assert "capability2_cross_metric_contradiction_narrator" in data
        assert "capability3_anomaly_materiality_triage" in data
        assert "capability5_contract_lapse_scanner" in data
        assert "capability6_payment_redirection_drift_detector" in data
        assert "capability9_executive_brief" in data
        assert "verification_audit_trail" in data

        # BEC drift verification
        bec = data["capability6_payment_redirection_drift_detector"][0]
        assert bec["drift_detected"] is True
        assert "GlobalRetail" in bec["counterparty"]


def test_spotlite_classify_endpoint():
    """Verify POST /api/v1/spotlite/augmented/classify handles stage 0 fallback classification."""
    with TestClient(app) as client:
        payload = {"narration": "ZOMATO B2B 000003007", "amount": 1500.0}
        response = client.post("/api/v1/spotlite/augmented/classify", json=payload)
        assert response.status_code == 200
        
        body = response.json()
        assert body["success"] is True
        assert body["data"]["canonical_entity"] == "Zomato Corporate"
        assert body["data"]["canonical_category"] == "Food Delivery"


def test_spotlite_ask_cfo_endpoint():
    """Verify POST /api/v1/spotlite/augmented/ask-cfo answers CFO queries with cell citations."""
    with TestClient(app) as client:
        payload = {"query": "Is a vendor overbilling me?"}
        response = client.post("/api/v1/spotlite/augmented/ask-cfo", json=payload)
        assert response.status_code == 200
        
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "85,000" in data["answer"] or "overbilling" in data["answer"].lower()
        assert data["verified_cell_citation"] == "tier1.vendor_overbilling_detector"


def test_spotlite_scenario_endpoint():
    """Verify POST /api/v1/spotlite/augmented/scenario simulates compound shocks."""
    with TestClient(app) as client:
        payload = {
            "churn_client_name": "Technova Solutions",
            "additional_hires": 2,
            "unresolved_overbilling_monthly": 85000.0
        }
        response = client.post("/api/v1/spotlite/augmented/scenario", json=payload)
        assert response.status_code == 200
        
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["additional_hires"] == 2
        assert data["projected_compound_runway_months"] > 0


if __name__ == "__main__":
    print("Running test_spotlite_tier1_metrics...")
    test_spotlite_tier1_metrics()
    print("PASSED")

    print("Running test_spotlite_tier2_metrics...")
    test_spotlite_tier2_metrics()
    print("PASSED")

    print("Running test_spotlite_llm_augmented_insights...")
    test_spotlite_llm_augmented_insights()
    print("PASSED")

    print("Running test_spotlite_classify_endpoint...")
    test_spotlite_classify_endpoint()
    print("PASSED")

    print("Running test_spotlite_ask_cfo_endpoint...")
    test_spotlite_ask_cfo_endpoint()
    print("PASSED")

    print("Running test_spotlite_scenario_endpoint...")
    test_spotlite_scenario_endpoint()
    print("PASSED")

    print("\nALL SPOTLITE API TESTS PASSED SUCCESSFULLY!")
