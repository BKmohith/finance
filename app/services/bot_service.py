"""
app/services/bot_service.py
Unified Omnichannel Copilot Service for Small Businesses.
Powers both Telegram Bot (@sahayak_retail_bot) and WhatsApp (Twilio & Meta).

Guarantees identical functionality across all chat channels:
1. Real-time counter sales & rate derivation with Agent 4 FIFO stock depletion.
2. Low stock & heading out of stock alerts (threshold <= 5 units).
3. Customer Khata ledger updates (Udhaar given & repayments collected).
4. Real-time inventory table (/stock) and customer receivables (/khata).
5. Dot-matrix paper bill digitization & wholesale price-hike defense (/simulate & photo uploads).
6. Vernacular voice notes & Indian audio processing (Sarvam AI STT + Jev Router).
"""
import asyncio
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from datetime import date, datetime
from sqlalchemy import select, and_, desc

from app.core.config import settings
from app.core.contracts import InboundIntentClass, PriceHikeAlert
from app.db import khata_repository, repository
from app.db.fifo_engine import get_stock_availability
from app.db.khata_models import InventoryBatch, CashTransaction, CustomerKhata
from app.db.models import PriceHistory, Invoice
from app.db.session import get_rls_session
from app.workers.jev_router import JevRouter
from app.workers.voice_khata import VoiceKhataParser
from app.services.closing_agent import closing_agent
from app.services.forecast_agent import forecast_agent

logger = logging.getLogger("sahayak.bot_service")


def format_counter_sale_receipt(sale, sale_res: dict) -> str:
    """
    Constructs a structured, human-readable counter sale receipt:
    - Inflow & Payment method badge
    - Rate calculation (Total / Qty)
    - FIFO inventory deduction & live shelf stock
    - Heading out of stock & out of stock alerts
    - Udhaar baaki updates (if credit extended)
    - Supabase ACID audit verification
    """
    lines = [
        "🧾 *Counter Sale Recorded!*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Settled Inflow:* ₹{sale.amount_paid:,.2f} ({sale.payment_method.value})"
    ]

    # Itemized Breakdown & Pricing Rates
    lines.append("\n📦 *Items Sold & Pricing:*")
    for item in sale.items:
        unit_str = f"/{item.unit}" if item.unit else ""
        lines.append(f" • *{item.item_name}*: `{item.quantity} {item.unit}` @ ₹{item.unit_retail_price:,.2f}{unit_str} (Total: ₹{item.line_total:,.2f})")

    # FIFO Inventory Depletion & Live Remaining Stock
    depletions = sale_res.get("inventory_depletions", [])
    if depletions:
        lines.append("\n🛡️ *Agent 4 FIFO Inventory Depletion:*")
        for dep in depletions:
            matched = dep.get("matched_sku", dep.get("item_name"))
            unit = dep.get("unit", "units")
            tot_dep = dep.get("total_depleted", 0.0)
            tot_rem = dep.get("total_remaining", 0.0)
            short = dep.get("shortfall", 0.0)

            lines.append(f" • *{matched}*:")
            lines.append(f"    ↳ *Depleted:* `{tot_dep} {unit}`")
            lines.append(f"    ↳ *Remaining Shelf Stock:* *`{tot_rem} {unit}`*")
            if short > 0:
                lines.append(f"    ⚠️ *Deficit:* `{short} {unit}` short on shelf (Zero-negative stock protected)")
            elif tot_rem == 0:
                lines.append(f"    🚨 *OUT OF STOCK:* You are completely out of stock for *{matched}*! Reorder immediately.")
            elif tot_rem <= 5:
                lines.append(f"    ⚠️ *Heading Out of Stock:* Only *`{tot_rem} {unit}`* left on shelf! Reorder soon from supplier.")

    # Customer Khata (Udhaar) Updates
    if sale.credit_amount > 0 and sale_res.get("customer_name"):
        c_bal = sale_res.get("customer_current_balance", 0.0)
        lines.append(f"\n👥 *Customer Khata Updated:*")
        lines.append(f" • *{sale_res['customer_name']}:* +₹{sale.credit_amount:,.2f} Udhaar Baaki (Total Baaki: *₹{c_bal:,.2f}*)")

    lines.append("\n🔒 *Ledger Status:* ACID Committed to Supabase PostgreSQL (RLS Enforced)")
    return "\n".join(lines)


def get_help_message() -> str:
    return (
        "✨ *Namaste! Welcome to Sahayak (सहायक)*\n\n"
        "I am your Autonomous Business Copilot for Indian Retail Dukandars.\n\n"
        "🛡️ *1. Agent 1: Margin Guard (Pure SQL / Jev)*\n"
        " • `/margin` or `/simulate` — Price-hike alerts & shelf repricing to protect gross margins\n\n"
        "📦 *2. Agent 2: Stock and Capital (Pure SQL / Jev)*\n"
        " • `/stock` or `/capital` — FIFO shelf stock & total working capital locked in inventory\n\n"
        "💧 *3. Agent 3: Liquidity (Pure SQL / Jev)*\n"
        " • `/liquidity` or `/cash` — Settled cash in hand, customer Udhaar receivables & payables\n\n"
        "🌙 *6. Agent 6: 10:15 PM Closing Agent (LLM + SQL Ledger)*\n"
        " • `/closing` or `/1015` — Nightly shop closing debrief synthesized from today's ledger records\n\n"
        "🔮 *7. Agent 7: What-If Agent (LLM + Database Stress-Testing)*\n"
        " • `/whatif [scenario]` — Financial shock stress tests & cash runway simulation\n"
        " • *Voice/Text:* \"Agar kal ITC ko 15000 du toh Saturday ko dukaan ka rent bachega kya?\"\n\n"
        "💵 *Daily Counter Operations:*\n"
        " • Sales: `28 units sunflower oil at price 8000` or `Paytm 300 Oil 2`\n"
        " • Khata: `Sharma ji 500 udhaar` or `Ramesh 200 jama`\n"
        " • Paper Bills: Snap & send photo to digitize into Margin-Guard"
    )


def handle_margin_query(merchant_id: str) -> str:
    """
    Agent 1: Margin Guard (Pure SQL / Jev - Zero LLM).
    Scans PriceHistory for wholesale supplier price hikes (>3%)
    and calculates exact recommended shelf MRP to protect gross margin.
    """
    try:
        with get_rls_session(merchant_id) as session:
            hikes = session.execute(
                select(PriceHistory)
                .where(PriceHistory.merchant_id == merchant_id)
                .order_by(desc(PriceHistory.recorded_at))
                .limit(10)
            ).scalars().all()

            if not hikes:
                return (
                    "🛡️ *Agent 1: Margin Guard (Price-Shield Ledger)*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "🟢 *Zero Wholesale Price Hikes Detected!* All purchase rates match baseline records.\n\n"
                    "💡 *Try:* `/simulate` to test wholesale price-hike defense on a sample distributor bill!\n"
                    "🔒 _100% Deterministic SQL • Zero LLM Hallucination Risk_"
                )

            lines = [
                "🛡️ *Agent 1: Margin Guard Price-Shield Alerts (Pure SQL)*",
                "━━━━━━━━━━━━━━━━━━━━",
                "⚠️ *Wholesale Price Deviations Detected in Invoices:*\n"
            ]
            for h in hikes:
                dt_str = h.recorded_at.strftime("%d-%b") if h.recorded_at else "Recent"
                rec_mrp = f" | Suggested MRP: ₹{h.suggested_retail_mrp:,.2f}" if h.suggested_retail_mrp else ""
                lines.append(
                    f" • *{h.item_name}* ({dt_str}):\n"
                    f"    ↳ Wholesale: ₹{h.old_wholesale_rate:,.2f} ➔ *₹{h.new_wholesale_rate:,.2f}* (+{h.percentage_hike:.1f}%)\n"
                    f"    ↳ Action: Protect margin with updated shelf MRP{rec_mrp}"
                )
            lines.append("\n🔒 _100% Deterministic SQL • Zero LLM Hallucination Risk_")
            return "\n".join(lines)
    except Exception as err:
        logger.error(f"Margin Guard query error: {err}", exc_info=True)
        return f"⚠️ Margin Guard error: {err}"


def handle_stock_and_capital_query(merchant_id: str) -> str:
    """
    Agent 2: Stock and Capital (Pure SQL / Jev - Zero LLM).
    Calculates active FIFO shelf stock, total working capital locked in inventory,
    and flags critical low stock / dead capital batches.
    """
    try:
        with get_rls_session(merchant_id) as session:
            batches = session.execute(
                select(InventoryBatch).where(
                    InventoryBatch.merchant_id == merchant_id,
                    InventoryBatch.quantity_remaining > 0
                ).order_by(InventoryBatch.quantity_remaining.asc())
            ).scalars().all()

            if not batches:
                return "📦 *Agent 2: Stock & Capital*\nInventory is empty. Snap and upload a wholesale bill photo to auto-stock batches!"

            total_capital = sum(b.quantity_remaining * (b.cost_price or 0.0) for b in batches)
            low_stock_count = sum(1 for b in batches if b.quantity_remaining <= 5.0)

            lines = [
                "📦 *Agent 2: Stock & Capital Intelligence (Pure SQL)*",
                "━━━━━━━━━━━━━━━━━━━━",
                f"💰 *Total Working Capital Locked in Stock:* *₹{total_capital:,.2f}*",
                f"📊 *Active FIFO Inventory Batches:* {len(batches)} batches",
                f"⚠️ *Low Stock Batches (<=5 units):* {low_stock_count}\n",
                "📋 *Shelf Inventory & Valuation Breakdown:*"
            ]

            for b in batches[:12]:
                val = b.quantity_remaining * (b.cost_price or 0.0)
                warn = " ⚠️ *(Low Stock!)*" if b.quantity_remaining <= 5.0 else ""
                lines.append(f" • *{b.item_name}*: `{b.quantity_remaining} {b.unit}` @ ₹{b.cost_price:,.2f} (Value: ₹{val:,.2f}){warn}")

            lines.append("\n🛡️ *Agent 4 FIFO Active:* Oldest batches are depleted first on checkout.")
            lines.append("🔒 _100% Deterministic SQL • Zero LLM Hallucination Risk_")
            return "\n".join(lines)
    except Exception as err:
        logger.error(f"Stock & Capital error: {err}", exc_info=True)
        return f"⚠️ Error fetching stock & capital: {err}"


# Backward compatibility alias
handle_stock_query = handle_stock_and_capital_query


def handle_liquidity_query(merchant_id: str) -> str:
    """
    Agent 3: Liquidity (Pure SQL / Jev - Zero LLM).
    Queries PostgreSQL for real-time settled cash in hand, active customer
    Udhaar receivables, and upcoming distributor payables.
    """
    try:
        with get_rls_session(merchant_id) as session:
            # 1. Settled Cash & UPI
            txns = session.execute(
                select(CashTransaction).where(CashTransaction.merchant_id == merchant_id)
            ).scalars().all()
            cash_tot = sum(t.amount for t in txns if t.payment_method == "CASH")
            upi_tot = sum(t.amount for t in txns if t.payment_method != "CASH")
            liquid_in_hand = cash_tot + upi_tot

            # 2. Receivables from Customer Khata
            khatas = session.execute(
                select(CustomerKhata).where(
                    and_(CustomerKhata.merchant_id == merchant_id, CustomerKhata.current_balance > 0)
                )
            ).scalars().all()
            receivables = sum(k.current_balance for k in khatas)
            debtors_cnt = len(khatas)

            # 3. Payables due to Distributors
            today = date.today()
            invoices = session.execute(
                select(Invoice).where(
                    and_(Invoice.merchant_id == merchant_id, Invoice.credit_due_date >= today)
                )
            ).scalars().all()
            payables = sum(inv.total_amount for inv in invoices)

            net_liquidity = liquid_in_hand + receivables - payables
            status_icon = "🟢" if net_liquidity >= 0 else "🚨"

            lines = [
                "💧 *Agent 3: Liquidity & Working Capital Ledger (Pure SQL)*",
                "━━━━━━━━━━━━━━━━━━━━",
                f"💵 *Settled Cash in Hand / Bank:* *₹{liquid_in_hand:,.2f}*",
                f" • 💵 Physical Cash: ₹{cash_tot:,.2f}",
                f" • 📱 Paytm UPI: ₹{upi_tot:,.2f}",
                f"📥 *Market Receivables (Customer Udhaar):* *+₹{receivables:,.2f}* ({debtors_cnt} active debtors)",
                f"📤 *Upcoming Distributor Payables:* *-₹{payables:,.2f}* ({len(invoices)} bills due)",
                "━━━━━━━━━━━━━━━━━━━━",
                f"{status_icon} *Net Immediate Liquidity Position:* *₹{net_liquidity:,.2f}*\n",
                "🔒 _100% Deterministic SQL • Zero LLM Hallucination Risk_"
            ]
            return "\n".join(lines)
    except Exception as err:
        logger.error(f"Liquidity query error: {err}", exc_info=True)
        return f"⚠️ Error fetching liquidity: {err}"


def handle_khata_query(merchant_id: str) -> str:
    """Fetches active customer store credit ledger and total receivables."""
    try:
        with get_rls_session(merchant_id) as session:
            khatas = khata_repository.list_merchant_khatas(session, merchant_id)

            if not khatas:
                return "👥 *No active customer Udhaar.* Say *'Sharma ji 500 udhaar'* to log store credit!"

            total_baaki = sum(k.current_balance for k in khatas if k.current_balance > 0)
            lines = [f"👥 *Customer Khata (Udhaar) Ledger*\n💰 *Total Receivables:* ₹{total_baaki:,.2f}\n"]
            for k in khatas[:15]:
                phone_str = f" ({k.customer_phone})" if k.customer_phone else ""
                status_icon = "🔴" if k.current_balance > 0 else "🟢"
                lines.append(f"{status_icon} *{k.customer_name}*{phone_str}: *₹{k.current_balance:,.2f}* baaki")
            return "\n".join(lines)
    except Exception as err:
        logger.error(f"Khata list error: {err}", exc_info=True)
        return f"⚠️ Error fetching Khata: {err}"


def handle_simulation_query(merchant_id: str, sender_phone: str = "") -> str:
    """Runs wholesale bill margin-defense simulation on sample price hike."""
    try:
        from app.api.notifier import AlertNotifier
        from app.workers.tasks import process_invoice_task

        res = process_invoice_task(
            merchant_id=merchant_id,
            media_id="sample_bill_SBT_2026_082_hike.jpg",
            whatsapp_message_id=f"sim_{merchant_id}_{int(time.time())}",
            sender_phone=sender_phone or "917338142740"
        )
        alerts_cnt = res.get("alerts_count", 0)
        lines = [
            f"⚡ *Price-Shield Margin Simulation Result:*\n",
            f"✅ *Test Invoice {res.get('invoice_number', 'Digitized')} Logged!*\n",
            f"📦 *Items Extracted:* {res.get('items_count', 0)} line items",
            f"💰 *Grand Total:* ₹{res.get('grand_total', 0):,.2f}",
            f"🛡️ *Price Hikes Detected:* {alerts_cnt}\n"
        ]

        margin_alerts = res.get("margin_alerts", [])
        for a_dict in margin_alerts:
            try:
                a_obj = PriceHikeAlert.model_validate(a_dict)
                lines.append(AlertNotifier.format_alert_message(a_obj))
                lines.append("")
            except Exception as a_err:
                logger.warning(f"Could not format alert in simulation: {a_err}")

        return "\n".join(lines)
    except Exception as err:
        logger.error(f"Simulation error: {err}", exc_info=True)
        return f"⚠️ Simulation error: {err}"


def format_gatekeeper_response(text: str) -> str:
    """
    Acts as Jev's domain gatekeeper response:
    - If greetings -> Warm Namaste with retail store actions.
    - If off-topic questions (e.g. 'what is AI', 'write code', general trivia) -> Explains retail store boundaries.
    """
    lower = text.lower().strip()
    greetings = ("hi", "hello", "hey", "good morning", "good evening", "namaste", "suprabhat")
    if any(lower.startswith(g) or lower == g for g in greetings):
        return (
            "🙏 *Namaste! Sahayak Copilot is ready.*\n\n"
            "I am your dedicated store copilot. Here is what I can do for your business:\n"
            " • 💵 *Record Counter Sale:* `28 units sunflower oil at price 8000`\n"
            " • 📖 *Record Customer Udhaar:* `Sharma ji 500 udhaar`\n"
            " • 📈 *Ask Retail Profit Advice:* _\"What should I sell to get more profit?\"_\n"
            " • 🔮 *Run What-If Cash Simulation:* _\"What happens if customers pay after 10 days?\"_\n"
            " • 📦 *View Shelf Stock:* `/stock`"
        )

    return (
        "🛡️ *Sahayak Business Gatekeeper (Topic Blocked)*\n\n"
        "I am your dedicated **Indian Retail Store & Financial Copilot**.\n"
        "To protect your store operations and keep your ledger focused, I strictly assist with:\n"
        " • 💵 Counter Sales & Itemized FIFO Depletion\n"
        " • 📖 Customer Udhaar (Khata Ledger)\n"
        " • 📈 Retail Profit Maximization & High-Margin Sourcing\n"
        " • 🔮 Cash Runway & 7-Day Forecasting\n"
        " • 📸 Wholesale Distributor Bill Digitization\n\n"
        "_Non-retail topics (such as general AI trivia, programming, coding, or chit-chat) are blocked._\n\n"
        "💡 *Try asking:* _\"What should I sell to get more profit?\"_ or _\"Who owes the most khata?\"_"
    )


def handle_text_message(merchant_id: str, user_text: str, sender_phone: str = "") -> str:
    """
    Main omnichannel text query handler:
    Directs commands, counter sales, and customer Khata entries.
    """
    clean_text = user_text.strip()
    if not clean_text:
        return get_help_message()

    lower = clean_text.lower()

    # 1. Start / Help / Join
    if clean_text in ("/start", "/help") or lower in ("help", "hi", "hello", "namaste", "start") or lower.startswith("join"):
        return get_help_message()

    # Agent 1: Margin Guard (Pure SQL / Zero LLM)
    if clean_text in ("/margin", "/margins", "/hike") or lower in ("margin", "margins", "price hike"):
        return handle_margin_query(merchant_id)

    if clean_text.startswith("/simulate") or clean_text.startswith("/test") or lower in ("simulate", "test"):
        return handle_simulation_query(merchant_id, sender_phone=sender_phone)

    # Agent 2: Stock and Capital (Pure SQL / Zero LLM)
    if clean_text in ("/stock", "/inventory", "/capital") or lower in ("stock", "inventory", "maal", "capital", "shelf", "shlef") or any(k in lower for k in ("shelf stock", "items on shelf", "item in shelf", "items in shelf", "in shelf", "in shlef")):
        return handle_stock_and_capital_query(merchant_id)

    # Agent 3: Liquidity (Pure SQL / Zero LLM)
    if clean_text in ("/liquidity", "/cash", "/runway") or lower in ("liquidity", "cash in hand", "liquid cash", "paisa"):
        return handle_liquidity_query(merchant_id)

    # Agent 6: 10:15 PM Closing & Daily Report Agent (LLM + SQL Ledger)
    closing_triggers = (
        "closing", "10:15", "1015", "dukaan band", "shubh ratri", "aaj ka hisab",
        "report of the day", "rport of the day", "report of day", "day report", "daily report",
        "today report", "today's report", "todays report", "create report", "create teh rport",
        "generate report", "din ka hisab", "aaj ki report", "daily debrief", "end of day",
        "summary of the day", "shop report", "dukaan report"
    )
    if clean_text in ("/closing", "/1015", "/nightly", "/report", "/daily") or any(k in lower for k in closing_triggers):
        return closing_agent.generate_closing_report(merchant_id)

    # Agent 7: What-If Agent (LLM + Database Stress-Testing)
    if clean_text.startswith("/whatif"):
        scenario_query = clean_text.replace("/whatif", "").strip()
        if not scenario_query:
            return "🔮 *Agent 7: What-If Stress Simulator*\nUsage: `/whatif Agar kal ITC ko 15000 du toh Saturday ko rent bachega kya?`"
        return forecast_agent.parse_and_simulate_query(merchant_id=merchant_id, query_text=scenario_query)

    # 7-day liquidity curve forecast
    if clean_text.startswith("/forecast") or lower in ("forecast", "cashflow"):
        days = 7
        parts = clean_text.strip().split()
        if len(parts) > 1 and parts[1].isdigit():
            days = min(max(int(parts[1]), 1), 30)
        f_data = forecast_agent.generate_forecast(merchant_id=merchant_id, forecast_days=days)
        return forecast_agent.format_telegram_report(f_data)

    # Customer Khata
    if clean_text in ("/khata", "/khatas", "/customers") or lower in ("khata", "udhaar", "customers"):
        return handle_khata_query(merchant_id)

    # Fast-Path Intent Routing (Counter Sales, Khata & Cash Forecast)
    is_explicit_sale = clean_text.startswith("/sale")
    is_explicit_khata = clean_text.startswith("/khata")
    is_explicit_forecast = clean_text.startswith("/forecast") or clean_text.startswith("/runway")

    route_text = clean_text
    if is_explicit_sale:
        route_text = clean_text.replace("/sale", "").strip()
    elif is_explicit_khata:
        route_text = clean_text.replace("/khata", "").strip()
    elif is_explicit_forecast:
        route_text = clean_text.replace("/forecast", "").replace("/runway", "").strip()

    router = JevRouter()
    intent = router.classify_intent(text=route_text)

    if is_explicit_sale:
        intent = InboundIntentClass.COUNTER_SALE
    elif is_explicit_khata:
        intent = InboundIntentClass.VOICE_KHATA
    elif is_explicit_forecast:
        intent = InboundIntentClass.CASH_FORECAST

    # A. MEME_SPAM Gatekeeper: Drop greetings, chit-chat, and off-topic spam without calling LLM fallback!
    if intent == InboundIntentClass.MEME_SPAM:
        logger.info(f"[JevGatekeeper] Intercepted MEME_SPAM text for merchant={merchant_id}: '{clean_text}'")
        greetings = ("hi", "hello", "hey", "namaste", "namaskara", "suprabhat", "good morning", "good evening", "good night", "kya haal", "kaise ho", "radhe radhe", "jai shree ram", "ram ram")
        if any(g in lower for g in greetings):
            return (
                "🙏 *Namaste! Welcome to Sahayak (सहायक)*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "I am your Autonomous Kirana & Retail Business Copilot.\n\n"
                "💡 *Quick Actions:*\n"
                " • 💵 *Record Sale:* `Paytm 300 Oil 2` or `25 bag atta 450 cash`\n"
                " • 📖 *Customer Khata:* `Sharma ji 500 udhaar` or `Ramesh 200 jama`\n"
                " • 📸 *Wholesale Bill:* Send photo of distributor invoice to track rates\n"
                " • 📦 *Commands:* `/stock` (inventory) | `/liquidity` (cash) | `/report` (daily debrief)"
            )
        return (
            "ℹ️ *Sahayak Retail Copilot*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "I specialize exclusively in your retail store's counter sales, customer Khata, wholesale bills, and stock.\n\n"
            "👉 *Examples of what I can do:*\n"
            " • `Paytm 300 Oil 2` — Log a counter sale\n"
            " • `Sharma ji 500 udhaar` — Record customer credit\n"
            " • `/stock` — View shelf inventory & capital\n"
            " • `/closing` — Nightly closing report"
        )

    # Agent 7: Real-Time Cash Forecast & What-If Runway (Natural Language via Jev Router)
    if intent == InboundIntentClass.CASH_FORECAST:
        what_if_triggers = ("agar", "what if", "what happens", "if i pay", "if the", "pays after", "after", "delay", "bachega kya", "rent bachega", "cheque bounce")
        if any(trig in lower for trig in what_if_triggers) or clean_text.endswith("?"):
            return forecast_agent.parse_and_simulate_query(merchant_id=merchant_id, query_text=clean_text)

        return handle_liquidity_query(merchant_id)

    # Business Intelligence & Agent 6 / 1 / 2 / 3 routing
    if intent == InboundIntentClass.BUSINESS_QUERY:
        if any(k in lower for k in closing_triggers):
            return closing_agent.generate_closing_report(merchant_id)
        if any(k in lower for k in ("liquidity", "liquid cash", "paisa kitna")):
            return handle_liquidity_query(merchant_id)
        if any(k in lower for k in ("stock", "capital", "inventory", "maal kitna", "shelf", "shlef", "item in", "items on", "items in", "what all")):
            return handle_stock_and_capital_query(merchant_id)
        if any(k in lower for k in ("margin", "price hike", "hike")):
            return handle_margin_query(merchant_id)
        from app.services.analytics_agent import analytics_agent
        return analytics_agent.answer_business_query(merchant_id=merchant_id, query=clean_text)

    # C. Counter Sale + FIFO Depletion
    if intent == InboundIntentClass.COUNTER_SALE:
        parser = VoiceKhataParser()
        sale_event = parser.parse_counter_sale(route_text, merchant_id=merchant_id)
        if sale_event:
            with get_rls_session(merchant_id) as session:
                repository.get_or_create_merchant(session=session, merchant_id=merchant_id)
                sale_res = khata_repository.record_counter_sale(session=session, merchant_id=merchant_id, sale=sale_event)
                return format_counter_sale_receipt(sale_event, sale_res)
        from app.services.copilot_llm import ask_copilot_llm
        return ask_copilot_llm(merchant_id=merchant_id, user_query=clean_text)

    # B. Customer Khata Entry
    if intent == InboundIntentClass.VOICE_KHATA:
        parser = VoiceKhataParser()
        khata_intent = parser.parse_voice_khata(route_text)
        if khata_intent:
            with get_rls_session(merchant_id) as session:
                repository.get_or_create_merchant(session=session, merchant_id=merchant_id)
                k_rec = khata_repository.record_khata_entry(
                    session=session,
                    merchant_id=merchant_id,
                    customer_name=khata_intent.customer_name,
                    amount=khata_intent.amount,
                    action=khata_intent.action,
                    phone=khata_intent.customer_phone,
                    notes=f"Chat Note: {clean_text}"
                )
                balance = k_rec.current_balance
                saved_phone = k_rec.customer_phone

            action_badge = f"Udhaar Diya (+₹{khata_intent.amount:,.2f})" if khata_intent.action == "GIVE_CREDIT" else f"Udhaar Chukaya (-₹{khata_intent.amount:,.2f})"
            phone_line = f"📞 *Phone:* `{saved_phone}`\n" if saved_phone else ""
            return (
                f"📖 *Customer Khata Updated!*\n\n"
                f"👤 *Customer:* {khata_intent.customer_name}\n"
                f"{phone_line}"
                f"💰 *Action:* {action_badge}\n"
                f"📊 *Current Udhaar Baaki:* ₹{balance:,.2f}\n"
                f"🔒 *Ledger Status:* ACID Committed to Supabase PostgreSQL (RLS Enforced)"
            )
        # If conversational Khata mention could not parse exact credit/repayment write, push to LLM Copilot
        from app.services.copilot_llm import ask_copilot_llm
        return ask_copilot_llm(merchant_id=merchant_id, user_query=clean_text)

    # =========================================================================
    # UNIVERSAL LLM COPILOT:
    # If the user message did not match an exact slash command, sale, or credit write,
    # PUSH DIRECTLY TO THE LLM (Gemini Flash) with live store dataset and guardrails!
    # =========================================================================
    from app.services.copilot_llm import ask_copilot_llm
    return ask_copilot_llm(merchant_id=merchant_id, user_query=clean_text)


def handle_voice_bytes(merchant_id: str, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribes audio, evaluates intent via JevRouter, and records transaction."""
    from app.workers.stt_engine import STTEngine
    stt = STTEngine()
    stt_res = stt.transcribe_audio(audio_bytes, filename)
    transcript = stt_res.get("transcription", "").strip()

    if not transcript:
        return "⚠️ Could not detect speech. Please speak clearly near your microphone."

    logger.info(f"Transcribed audio for {merchant_id}: '{transcript}'")
    router = JevRouter()
    intent = router.classify_intent(text=transcript)

    # Route A: Customer Khata
    if intent == InboundIntentClass.VOICE_KHATA:
        parser = VoiceKhataParser()
        khata_intent = parser.parse_voice_khata(transcript)
        if khata_intent:
            with get_rls_session(merchant_id) as session:
                repository.get_or_create_merchant(session=session, merchant_id=merchant_id)
                k_rec = khata_repository.record_khata_entry(
                    session=session,
                    merchant_id=merchant_id,
                    customer_name=khata_intent.customer_name,
                    amount=khata_intent.amount,
                    action=khata_intent.action,
                    phone=khata_intent.customer_phone,
                    notes=f"Voice Note: {transcript}"
                )
                balance = k_rec.current_balance
                saved_phone = k_rec.customer_phone

            action_badge = f"Udhaar Diya (+₹{khata_intent.amount:,.2f})" if khata_intent.action == "GIVE_CREDIT" else f"Udhaar Chukaya (-₹{khata_intent.amount:,.2f})"
            phone_line = f"📞 *Phone:* `{saved_phone}`\n" if saved_phone else ""
            return (
                f"🎙️ *Heard:* \"{transcript}\"\n\n"
                f"📖 *Customer Khata Updated!*\n"
                f"👤 *Customer:* {khata_intent.customer_name}\n"
                f"{phone_line}"
                f"💰 *Action:* {action_badge}\n"
                f"📊 *Current Udhaar Baaki:* ₹{balance:,.2f}\n"
                f"🔒 *Ledger Status:* ACID Committed to Supabase PostgreSQL (RLS Active)"
            )

    # Route B: Counter Sale
    if intent == InboundIntentClass.COUNTER_SALE:
        parser = VoiceKhataParser()
        sale_event = parser.parse_counter_sale(transcript, merchant_id=merchant_id)
        if sale_event:
            with get_rls_session(merchant_id) as session:
                repository.get_or_create_merchant(session=session, merchant_id=merchant_id)
                sale_res = khata_repository.record_counter_sale(session=session, merchant_id=merchant_id, sale=sale_event)
                receipt = format_counter_sale_receipt(sale_event, sale_res)
                return f"🎙️ *Heard:* \"{transcript}\"\n\n{receipt}"

    # Route C: Agent 5 Real-Time Cash Forecast & What-If Runway
    if intent == InboundIntentClass.CASH_FORECAST:
        from app.services.forecast_agent import forecast_agent
        what_if_triggers = ("agar", "what if", "if i pay", "agar kal", "agar me", "bachega kya", "rent bachega", "cheque bounce hoga")
        lower_t = transcript.lower()
        if any(trig in lower_t for trig in what_if_triggers):
            report = forecast_agent.parse_and_simulate_query(merchant_id=merchant_id, query_text=transcript)
            return f"🎙️ *Heard:* \"{transcript}\"\n\n{report}"

        f_data = forecast_agent.generate_forecast(merchant_id=merchant_id, forecast_days=7)
        report = forecast_agent.format_telegram_report(f_data)
        return f"🎙️ *Heard:* \"{transcript}\"\n\n{report}"

    # Route D: Universal Copilot Fallback (Push to LLM with Store Dataset & Guardrails)
    return handle_text_message(merchant_id=merchant_id, user_text=transcript)


def handle_bill_image_bytes(merchant_id: str, image_bytes: bytes, filename: str, sender_phone: str = "") -> str:
    """Saves bill image to local storage, runs OCR via Gemini Vision, and returns alert breakdown."""
    from app.services.image_gatekeeper import classify_image_document
    gate_res = classify_image_document(image_bytes)
    if not gate_res.is_invoice:
        return gate_res.rejection_message

    from app.workers.tasks import process_invoice_task
    from app.api.notifier import AlertNotifier

    # Save image to scratch/temp folder
    save_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scratch", "invoices")
    os.makedirs(save_dir, exist_ok=True)
    media_id = f"wa_{int(time.time())}_{uuid.uuid4().hex[:6]}_{filename}"
    file_path = os.path.join(save_dir, media_id)

    with open(file_path, "wb") as f:
        f.write(image_bytes)

    res = process_invoice_task(
        merchant_id=merchant_id,
        media_id=file_path,
        whatsapp_message_id=f"msg_{int(time.time())}",
        sender_phone=sender_phone or "917338142740"
    )

    if res.get("status") == "REJECTED_NON_INVOICE":
        from app.services.image_gatekeeper import format_rejection_message
        return format_rejection_message("other", res.get("reason", "No commercial billing line items detected."))

    alerts_cnt = res.get("alerts_count", 0)
    lines = [
        f"🧾 *Wholesale Bill Processed & Digitized!*\n",
        f"🏢 *Distributor/Supplier:* {res.get('supplier_name', 'Wholesale Partner')}",
        f"📄 *Invoice No:* `{res.get('invoice_number', 'Digitized')}`",
        f"📦 *Items Extracted:* {res.get('items_count', 0)} line items",
        f"💰 *Grand Total:* ₹{res.get('grand_total', 0):,.2f}",
        f"🛡️ *Margin-Guard Alerts:* {alerts_cnt}\n"
    ]

    margin_alerts = res.get("margin_alerts", [])
    for a_dict in margin_alerts:
        try:
            a_obj = PriceHikeAlert.model_validate(a_dict)
            lines.append(AlertNotifier.format_alert_message(a_obj))
            lines.append("")
        except Exception as a_err:
            logger.warning(f"Could not format alert: {a_err}")

    lines.append("🔒 *Stock Batches Added to Supabase PostgreSQL (FIFO Active)*")
    return "\n".join(lines)
