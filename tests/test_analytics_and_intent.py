"""
tests/test_analytics_and_intent.py
Verifies:
1. Questions like "What happens if the coustomer pays the khata after 10 days" are classified as CASH_FORECAST (never VOICE_KHATA).
2. Person inquiries like "Tell me about Sharma ji" are classified as BUSINESS_QUERY.
3. AnalyticsAgent creates structured customer dossiers from SQL records.
4. Top debtors analytical queries return ranked scorecards.
"""
import pytest
from app.core.contracts import InboundIntentClass
from app.workers.jev_router import jev_router
from app.services.forecast_agent import forecast_agent
from app.services.analytics_agent import analytics_agent


def test_what_if_delay_intent_not_khata():
    """Confirms user screenshot query is classified as CASH_FORECAST, never mistaken for transactional Udhaar."""
    query = "What happens if the coustomer pays the khata after 10 days"
    intent = jev_router.classify_intent(text=query)
    assert intent == InboundIntentClass.CASH_FORECAST


def test_what_if_delay_simulation_execution():
    """Verifies that the What-If simulation accurately detects the 10-day repayment lag."""
    query = "What happens if the coustomer pays the khata after 10 days"
    report = forecast_agent.parse_and_simulate_query(merchant_id="M_TEST_ANALYTICS", query_text=query)
    assert "Customer Khata Repayment Lag" in report
    assert "10 Days" in report
    assert "Agent 5" in report


def test_person_inquiry_classified_as_business_query():
    """Confirms questions about a person or customer are classified as BUSINESS_QUERY."""
    query = "Tell me about Sharma ji"
    intent = jev_router.classify_intent(text=query)
    assert intent == InboundIntentClass.BUSINESS_QUERY


def test_analytics_agent_top_debtors():
    """Verifies the SQL analytics agent answers debtor ranking questions."""
    res = analytics_agent.answer_business_query(
        merchant_id="M_TEST_ANALYTICS",
        query="Who owes the most khata?"
    )
    assert "Customer" in res or "Udhaar" in res


def test_direct_transactional_khata_still_works():
    """Ensures true transactional entries like 'Sharma ji 500 udhaar' still classify as VOICE_KHATA fast."""
    txn_text = "Sharma ji 500 udhaar"
    intent = jev_router.classify_intent(text=txn_text)
    assert intent == InboundIntentClass.VOICE_KHATA


def test_counter_sale_oil_arithmetic_normalization():
    """Verifies user query '28 units of sunflower oil at price 8000' parses without Pydantic validation error."""
    from app.workers.voice_khata import VoiceKhataParser
    query = "28 units of sunflower oil at price 8000"
    intent = jev_router.classify_intent(text=query)
    assert intent == InboundIntentClass.COUNTER_SALE

    parser = VoiceKhataParser()
    sale = parser.parse_counter_sale(query, merchant_id="M_TEST_OIL")
    assert sale is not None
    assert len(sale.items) == 1
    item = sale.items[0]
    assert item.quantity == 28.0
    assert item.line_total == 8000.0
    assert item.unit_retail_price == 285.71
    assert sale.amount_paid == 8000.0

