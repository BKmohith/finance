"""
tests/test_phase3_forecast.py
Comprehensive Phase 3 Test Suite:
1. Debtor Repayment Reliability Scoring (Tiers A/B/C: 90%, 70%, 20%).
2. Rolling 7/15/30-day liquidity curves & daily trajectory generation.
3. The 4 Financial Shock Vectors (Emergency Expense, Khata Lag, Revenue Slump, Supplier Shift).
4. Corrective Action Decision Matrix verification.
5. Conversational What-If parsing and simulation reports.
6. REST API integration: GET /api/counter/forecast & POST /api/counter/simulate.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.forecast_agent import CashForecastAgent, forecast_agent


def test_debtor_repayment_reliability_tiers():
    """Verifies that customers are scored accurately based on settlement velocity."""
    agent = CashForecastAgent()

    # Tier A: Prompt Payer (<= 7 days) -> 90%
    tier_a = agent.score_debtor_reliability(balance=1000.0, entry_count=5, last_payment_days=3)
    assert "Tier A" in tier_a["tier"]
    assert tier_a["probability"] == 0.90
    assert tier_a["weighted_amount"] == 900.0

    # Tier B: Standard Payer (8-20 days) -> 70%
    tier_b = agent.score_debtor_reliability(balance=2000.0, entry_count=3, last_payment_days=14)
    assert "Tier B" in tier_b["tier"]
    assert tier_b["probability"] == 0.70
    assert tier_b["weighted_amount"] == 1400.0

    # Tier C: Slow / Chronic Debtor (> 20 days or no payments) -> 20%
    tier_c = agent.score_debtor_reliability(balance=3000.0, entry_count=1, last_payment_days=35)
    assert "Tier C" in tier_c["tier"]
    assert tier_c["probability"] == 0.20
    assert tier_c["weighted_amount"] == 600.0

    # Tier C with no payment history
    tier_c_none = agent.score_debtor_reliability(balance=500.0, entry_count=0, last_payment_days=None)
    assert "Tier C" in tier_c_none["tier"]
    assert tier_c_none["probability"] == 0.20
    assert tier_c_none["weighted_amount"] == 100.0


def test_forecast_trajectory_and_decision_matrix():
    """Confirms daily trajectory vector generation and corrective decision matrix."""
    agent = CashForecastAgent()
    data = agent.generate_forecast(merchant_id="M_TEST_P3", forecast_days=7)

    assert "current_liquid_cash" in data
    assert "total_khata_receivables" in data
    assert "expected_receivables_weighted" in data
    assert "committed_supplier_payables" in data
    assert "projected_balance" in data
    assert "trajectory" in data
    assert len(data["trajectory"]) == 8  # Day 0 to Day 7 inclusive

    # Check trajectory items
    for item in data["trajectory"]:
        assert "date" in item
        assert "projected_balance" in item
        assert item["status"] in ("SAFE", "TIGHT", "CRUNCH")

    # Corrective action recommendations must exist
    assert len(data["recommendations"]) >= 1


def test_shock_vector_emergency_expense():
    """Simulates an unexpected capital shock (e.g. ₹6,000 emergency repair)."""
    agent = CashForecastAgent()
    res = agent.simulate_scenario(
        merchant_id="M_TEST_P3",
        shock_vector="EMERGENCY_EXPENSE",
        shock_amount=6000.0,
        forecast_days=7
    )

    assert res["shock_vector"] == "EMERGENCY_EXPENSE"
    assert res["parameters"]["shock_amount"] == 6000.0
    # Net delta must reflect the -₹6,000 shock exactly
    assert res["net_impact_delta"] == -6000.0
    assert res["stressed_projected_balance"] == res["baseline_projected_balance"] - 6000.0
    assert len(res["stressed_trajectory"]) == 8


def test_shock_vector_revenue_slump():
    """Simulates a 30% unseasonal walk-in sales reduction."""
    agent = CashForecastAgent()
    res = agent.simulate_scenario(
        merchant_id="M_TEST_P3",
        shock_vector="REVENUE_SLUMP",
        slump_pct=30.0,
        forecast_days=7
    )

    assert res["shock_vector"] == "REVENUE_SLUMP"
    assert res["parameters"]["slump_pct"] == 30.0
    assert res["stressed_projected_balance"] <= res["baseline_projected_balance"]


def test_conversational_what_if_query_formatting():
    """Verifies that natural what-if queries return structured Telegram reports."""
    agent = CashForecastAgent()
    query = "Agar kal ITC ko 15000 du toh Saturday ko dukaan ka rent bachega kya?"
    report = agent.parse_and_simulate_query(merchant_id="M_TEST_P3", query_text=query)

    assert "Agent 5: \"What-If\" Liquidity Simulation" in report
    assert "Simulation Balance Trajectory" in report
    assert "ACID Verified Python Math" in report


def test_api_counter_forecast_endpoint():
    """Tests GET /api/counter/forecast endpoint."""
    client = TestClient(app)
    resp = client.get("/api/counter/forecast?merchant_id=M_TEST_P3&days=7")
    assert resp.status_code == 200
    data = resp.json()

    assert data["forecast_days"] == 7
    assert "projected_balance" in data
    assert "trajectory" in data
    assert "recommendations" in data


def test_api_counter_simulate_endpoint():
    """Tests POST /api/counter/simulate endpoint."""
    client = TestClient(app)
    payload = {
        "merchant_id": "M_TEST_P3",
        "shock_vector": "EMERGENCY_EXPENSE",
        "shock_amount": 4500.0,
        "forecast_days": 15
    }
    resp = client.post("/api/counter/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["shock_vector"] == "EMERGENCY_EXPENSE"
    assert data["net_impact_delta"] == -4500.0
    assert "baseline_trajectory" in data
    assert "stressed_trajectory" in data
