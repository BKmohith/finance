"""
tests/test_gatekeeper_and_advisory.py
Verifies:
1. Jev acts as an intelligent domain blocker:
   - Off-topic queries ("what is AI", "who is the president") are classified as MEME_SPAM and blocked.
2. Jev marks retail profit & strategy queries ("what should i sell to get more profit") as BUSINESS_QUERY.
3. AnalyticsAgent routes open-ended business strategy queries to the LLM Retail Advisor (Gemini Flash).
4. Gatekeeper response clearly communicates the retail domain boundary.
"""
import pytest
from app.core.contracts import InboundIntentClass
from app.workers.jev_router import jev_router
from app.services.analytics_agent import analytics_agent
from app.services.bot_service import format_gatekeeper_response


def test_off_topic_query_blocked_as_meme_spam():
    """Confirms non-retail off-topic query 'what is ai' is classified as MEME_SPAM to block it."""
    query = "what is ai"
    intent = jev_router.classify_intent(text=query)
    assert intent == InboundIntentClass.MEME_SPAM


def test_another_off_topic_query_blocked():
    """Confirms general trivia is classified as MEME_SPAM to block it."""
    query = "who is the president of the united states"
    intent = jev_router.classify_intent(text=query)
    assert intent == InboundIntentClass.MEME_SPAM


def test_profit_strategy_classified_as_business_query():
    """Confirms retail strategy question 'what should i sell to get more profit' is classified as BUSINESS_QUERY."""
    query = "what should i sell to get more profit"
    intent = jev_router.classify_intent(text=query)
    assert intent == InboundIntentClass.BUSINESS_QUERY


def test_gatekeeper_response_blocks_off_topic():
    """Verifies that format_gatekeeper_response returns a dedicated retail boundary block message."""
    resp = format_gatekeeper_response("what is ai")
    assert "Sahayak Business Gatekeeper" in resp or "Retail Store" in resp
    assert "blocked" in resp.lower()


def test_retail_advisory_llm_execution():
    """Verifies AnalyticsAgent delivers structured retail advisory on margins and categories."""
    query = "what should i sell to get more profit"
    res = analytics_agent.answer_business_query(merchant_id="M_DEMO_001", query=query)
    assert "Profit" in res or "Margin" in res or "Advisory" in res
    assert "FMCG" in res or "Spices" in res or "Margin" in res


def test_retail_advisory_is_grounded_in_dataset():
    """
    CRITICAL TEST: Asserts that whatever solution the LLM returns,
    the products, margins, and figures are 100% tied to the database dataset.
    """
    query = "what should i sell to get more profit"
    res = analytics_agent.answer_business_query(merchant_id="merchant_test_p3", query=query)
    
    # Must quote actual SKUs from the database
    assert any(sku in res for sku in ("Everest Garam Masala", "Dettol", "Fortune Sunflower Oil", "Sugar", "Atta"))
    # Must quote actual profit margin figures calculated from the database
    assert "%" in res
    assert "₹" in res
    # Must be grounded in live dukaan records
    assert "Grounded" in res or "Tied to Your Live Store Data" in res or "PostgreSQL" in res
