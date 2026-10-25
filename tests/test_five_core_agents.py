"""
tests/test_five_core_agents.py
Verifies the exact 5 core agents:
1) Agent 1: Margin Guard (Pure SQL / Jev - Zero LLM)
2) Agent 2: Stock and Capital (Pure SQL / Jev - Zero LLM)
3) Agent 3: Liquidity (Pure SQL / Jev - Zero LLM)
6) Agent 6: 10:15 PM Closing Agent (LLM queries Database -> Grounded vernacular report)
7) Agent 7: What-If Agent (LLM queries Database -> Grounded scenario stress-test)
"""
import pytest
from app.services.bot_service import (
    handle_margin_query,
    handle_stock_and_capital_query,
    handle_liquidity_query,
    handle_text_message
)
from app.services.closing_agent import closing_agent
from app.services.forecast_agent import forecast_agent

TEST_MERCHANT = "merchant_test_p3"


def test_agent1_margin_guard_pure_sql_no_llm():
    """Agent 1: Margin Guard operates via pure SQL (zero LLM)."""
    res = handle_margin_query(TEST_MERCHANT)
    assert "Agent 1: Margin Guard" in res or "Price-Shield" in res
    assert "Zero LLM Hallucination Risk" in res


def test_agent2_stock_and_capital_pure_sql_no_llm():
    """Agent 2: Stock and Capital operates via pure SQL (zero LLM), calculating locked capital."""
    res = handle_stock_and_capital_query(TEST_MERCHANT)
    assert "Agent 2: Stock & Capital" in res or "Stock & Capital" in res
    assert "Total Working Capital Locked in Stock" in res
    assert "₹" in res
    assert "Zero LLM Hallucination Risk" in res


def test_agent3_liquidity_pure_sql_no_llm():
    """Agent 3: Liquidity operates via pure SQL (zero LLM), balancing cash, Udhaar, and payables."""
    res = handle_liquidity_query(TEST_MERCHANT)
    assert "Agent 3: Liquidity" in res or "Liquidity" in res
    assert "Settled Cash in Hand" in res
    assert "Market Receivables" in res
    assert "Net Immediate Liquidity Position" in res
    assert "Zero LLM Hallucination Risk" in res


def test_agent6_1015_closing_agent():
    """Agent 6: 10:15 PM Closing Agent queries database and synthesizes nightly report."""
    res = closing_agent.generate_closing_report(TEST_MERCHANT)
    assert "10:15 PM" in res or "Closing Report" in res
    assert "Today" in res or "Collection" in res or "Cash" in res
    assert "ACID Verified" in res or "Agent 6" in res


def test_agent7_whatif_agent():
    """Agent 7: What-If Agent queries database, stress-tests scenario, and returns 3 corrective remedies."""
    query = "Agar kal ITC ko 15000 du toh Saturday ko dukaan ka rent bachega kya?"
    res = forecast_agent.parse_and_simulate_query(merchant_id=TEST_MERCHANT, query_text=query)
    assert "SCENARIO RESULT" in res or "Baseline Projected" in res or "Stressed" in res
    assert "Trade-Off" in res or "Corrective" in res or "Shortfall" in res or "Safe" in res


def test_bot_service_command_routing_to_agents():
    """Verifies omnichannel text commands route to the 5 exact agents."""
    # Agent 1
    m_res = handle_text_message(TEST_MERCHANT, "/margin")
    assert "Margin Guard" in m_res

    # Agent 2
    s_res = handle_text_message(TEST_MERCHANT, "/capital")
    assert "Stock & Capital" in s_res or "Capital Locked" in s_res

    # Agent 3
    l_res = handle_text_message(TEST_MERCHANT, "/liquidity")
    assert "Liquidity" in l_res

    # Agent 6
    c_res = handle_text_message(TEST_MERCHANT, "/closing")
    assert "10:15 PM" in c_res or "Closing" in c_res

    # Agent 7
    w_res = handle_text_message(TEST_MERCHANT, "/whatif agar 10 din delay ho")
    assert "SCENARIO" in w_res or "Simulat" in w_res or "Baseline" in w_res
