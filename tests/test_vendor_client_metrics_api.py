"""
Test suite for Vendor Analytics (with Fixed/Variable Debits) and Client Analytics APIs
"""

import sys
import os
from fastapi.testclient import TestClient

# Ensure app is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


def test_vendor_metrics_api():
    """Verify GET /api/v1/cfo/vendors/metrics returns vendor info & fixed/variable debits classification."""
    with TestClient(app) as client:
        response = client.get("/api/v1/cfo/vendors/metrics")
        assert response.status_code == 200, f"Unexpected status code: {response.status_code}"

        body = response.json()
        assert body["success"] is True
        data = body["data"]

        # Verify components
        assert "summary" in data
        assert "vendor_directory_and_metrics" in data
        assert "fixed_vs_variable_debits_classification" in data
        assert "vendor_overbilling_anomalies" in data
        assert "single_vendor_dependency_risks" in data

        # Verify fixed vs variable debits classification
        f_v = data["fixed_vs_variable_debits_classification"]
        assert "Cloud Infrastructure" in f_v["fixed_categories"]
        assert "Cab Services" in f_v["variable_categories"]
        assert f_v["fixed_debits_monthly"] > 0
        assert f_v["variable_debits_monthly"] > 0

        # Verify overbilling anomalies
        anom = data["vendor_overbilling_anomalies"]
        assert len(anom) > 0
        assert anom[0]["vendor_id"] is not None


def test_client_metrics_api():
    """Verify GET /api/v1/cfo/clients/metrics returns client info & monthly revenue matrix."""
    with TestClient(app) as client:
        response = client.get("/api/v1/cfo/clients/metrics")
        assert response.status_code == 200, f"Unexpected status code: {response.status_code}"

        body = response.json()
        assert body["success"] is True
        data = body["data"]

        # Verify components
        assert "summary" in data
        assert "client_directory_and_metrics" in data
        assert "monthly_revenue_matrix" in data
        assert "client_concentration_radar" in data
        assert "client_payment_date_drift" in data
        assert "top_client_churn_scenario_simulation" in data

        # Verify client concentration radar
        radar = data["client_concentration_radar"]
        assert "Technova" in radar["top1_client_name"]
        assert radar["top1_client_share_pct"] > 0

        # Verify revenue matrix
        matrix = data["monthly_revenue_matrix"]
        assert "Technova Solutions" in matrix


def test_spotlite_vendor_client_convenience_endpoints():
    """Verify convenience routes under /api/v1/spotlite/vendors/analytics and /api/v1/spotlite/clients/analytics."""
    with TestClient(app) as client:
        r_v = client.get("/api/v1/spotlite/vendors/analytics")
        assert r_v.status_code == 200
        assert r_v.json()["success"] is True

        r_c = client.get("/api/v1/spotlite/clients/analytics")
        assert r_c.status_code == 200
        assert r_c.json()["success"] is True


if __name__ == "__main__":
    print("Running test_vendor_metrics_api...")
    test_vendor_metrics_api()
    print("PASSED")

    print("Running test_client_metrics_api...")
    test_client_metrics_api()
    print("PASSED")

    print("Running test_spotlite_vendor_client_convenience_endpoints...")
    test_spotlite_vendor_client_convenience_endpoints()
    print("PASSED")

    print("\nALL VENDOR & CLIENT METRICS API TESTS PASSED SUCCESSFULLY!")
