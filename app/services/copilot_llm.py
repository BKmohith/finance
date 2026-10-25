"""
app/services/copilot_llm.py
Universal Gemini Fallback Copilot for Sahayak.
JEv routes questions that existing AI components cannot handle to Gemini.

When Gemini receives a question:
1. Retrieve the relevant database information for the current request through the authorized backend.
2. Respect the authenticated merchant's identity and existing database RLS policies.
3. Analyze the retrieved data and generate a useful answer that directly addresses the user's question.
4. You may create new explanatory sentences, calculations, and relevant recommendations based on the retrieved data.
5. Keep the final response to approximately 100 words maximum.
6. Focus only on the user's question and the main topic. Avoid unrelated information, lengthy explanations, unnecessary introductions, and excessive lists.
7. Never invent database facts or present unsupported assumptions as verified information.
8. If the required data is unavailable, explain the limitation briefly.
9. Do not expose another merchant's data, credentials, or private information.
10. Do not change JEv's existing routing logic or interfere with AI components that already handle supported questions.
"""
from datetime import datetime, date, timedelta
import logging
import re
from typing import Dict, Any, List
from sqlalchemy import select, and_, desc

from app.workers.config import settings
from app.db.session import get_rls_session
from app.db.khata_models import CashTransaction, CustomerKhata, KhataEntry, InventoryBatch
from app.db.models import Invoice, Merchant, PriceHistory

logger = logging.getLogger("sahayak.copilot_llm")


def gather_live_store_dataset(merchant_id: str) -> Dict[str, Any]:
    """
    Pulls complete, real-time snapshot of the merchant's store ledger from PostgreSQL:
    1. Merchant account details
    2. Inventory batches & shelf stock
    3. Today's counter cash and UPI collections
    4. Recent cash transactions (context)
    5. Customer Udhaar accounts & receivables
    6. Distributor payables & upcoming due bills
    7. Wholesale price hikes
    Strictly scoped to merchant_id and respects PostgreSQL RLS policies.
    """
    clean_merchant = merchant_id.strip()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    store_data: Dict[str, Any] = {
        "merchant_name": "Kirana Store",
        "merchant_id": clean_merchant,
        "date_str": date.today().strftime("%d-%b-%Y"),
        "inventory": [],
        "total_stock_value": 0.0,
        "low_stock_items": [],
        "today_sales": {
            "cash": 0.0,
            "upi": 0.0,
            "total": 0.0,
            "count": 0,
        },
        "recent_transactions": [],
        "khata": {
            "total_receivables": 0.0,
            "debtors_count": 0,
            "customers": [],
            "today_credit_given": 0.0,
            "today_credit_collected": 0.0,
        },
        "payables": {
            "total_due": 0.0,
            "bills": [],
        },
        "price_hikes": [],
    }

    try:
        with get_rls_session(clean_merchant) as session:
            # 1. Merchant info
            m = session.execute(select(Merchant).where(Merchant.id == clean_merchant)).scalar_one_or_none()
            if m and m.name:
                store_data["merchant_name"] = m.name

            # 2. Inventory batches (active remaining shelf stock)
            batches = session.execute(
                select(InventoryBatch).where(
                    and_(InventoryBatch.merchant_id == clean_merchant, InventoryBatch.quantity_remaining > 0)
                ).order_by(InventoryBatch.quantity_remaining.asc())
            ).scalars().all()

            for b in batches:
                cost = b.cost_price or 0.0
                qty = b.quantity_remaining or 0.0
                mrp = b.retail_mrp or round(cost * 1.12, 2)
                margin = round(mrp - cost, 2)
                margin_pct = round((margin / cost * 100), 1) if cost > 0 else 0.0
                val = round(qty * cost, 2)
                store_data["total_stock_value"] += val

                item_info = {
                    "item_name": b.item_name,
                    "quantity": qty,
                    "unit": b.unit,
                    "cost_price": cost,
                    "retail_mrp": mrp,
                    "unit_margin": margin,
                    "margin_pct": margin_pct,
                    "batch_value": val,
                }
                store_data["inventory"].append(item_info)

                if qty <= 5.0:
                    store_data["low_stock_items"].append(f"{b.item_name} ({qty} {b.unit} left)")

            store_data["total_stock_value"] = round(store_data["total_stock_value"], 2)

            # 3. Today's counter cash and UPI collections
            txns = session.execute(
                select(CashTransaction).where(
                    and_(CashTransaction.merchant_id == clean_merchant, CashTransaction.created_at >= today_start)
                )
            ).scalars().all()

            for t in txns:
                amt = float(t.amount or 0.0)
                store_data["today_sales"]["total"] += amt
                store_data["today_sales"]["count"] += 1
                if t.payment_method == "CASH":
                    store_data["today_sales"]["cash"] += amt
                else:
                    store_data["today_sales"]["upi"] += amt

            store_data["today_sales"]["cash"] = round(store_data["today_sales"]["cash"], 2)
            store_data["today_sales"]["upi"] = round(store_data["today_sales"]["upi"], 2)
            store_data["today_sales"]["total"] = round(store_data["today_sales"]["total"], 2)

            # 4. Recent transactions context (last 5)
            recent_txns = session.execute(
                select(CashTransaction).where(CashTransaction.merchant_id == clean_merchant)
                .order_by(desc(CashTransaction.created_at)).limit(5)
            ).scalars().all()
            for rt in recent_txns:
                store_data["recent_transactions"].append({
                    "amount": float(rt.amount or 0.0),
                    "method": rt.payment_method,
                    "time": rt.created_at.strftime("%d-%b %H:%M") if rt.created_at else "Recent"
                })

            # 5. Customer Khata receivables & debtors
            khatas = session.execute(
                select(CustomerKhata).where(
                    and_(CustomerKhata.merchant_id == clean_merchant, CustomerKhata.current_balance > 0)
                ).order_by(desc(CustomerKhata.current_balance))
            ).scalars().all()

            for k in khatas:
                bal = float(k.current_balance or 0.0)
                store_data["khata"]["total_receivables"] += bal
                store_data["khata"]["customers"].append({
                    "name": k.customer_name,
                    "balance": bal,
                    "phone": k.customer_phone or "",
                })
            store_data["khata"]["debtors_count"] = len(khatas)
            store_data["khata"]["total_receivables"] = round(store_data["khata"]["total_receivables"], 2)

            # Today's Khata credit activity
            entries_today = session.execute(
                select(KhataEntry).where(
                    and_(KhataEntry.merchant_id == clean_merchant, KhataEntry.created_at >= today_start)
                )
            ).scalars().all()
            for e in entries_today:
                if e.action == "GIVE_CREDIT":
                    store_data["khata"]["today_credit_given"] += float(e.amount or 0.0)
                elif e.action == "COLLECT_PAYMENT":
                    store_data["khata"]["today_credit_collected"] += float(e.amount or 0.0)

            # 6. Payables due to wholesale suppliers
            today = date.today()
            invoices = session.execute(
                select(Invoice).where(
                    and_(Invoice.merchant_id == clean_merchant, Invoice.credit_due_date >= today)
                ).order_by(Invoice.credit_due_date.asc())
            ).scalars().all()

            for inv in invoices:
                tot = float(inv.total_amount or 0.0)
                store_data["payables"]["total_due"] += tot
                store_data["payables"]["bills"].append({
                    "supplier": inv.supplier_name,
                    "amount": tot,
                    "due_date": inv.credit_due_date.strftime("%d-%b-%Y") if inv.credit_due_date else "Due",
                })
            store_data["payables"]["total_due"] = round(store_data["payables"]["total_due"], 2)

            # 7. Price history
            hikes = session.execute(
                select(PriceHistory).where(PriceHistory.merchant_id == clean_merchant)
                .order_by(desc(PriceHistory.recorded_at)).limit(5)
            ).scalars().all()
            for h in hikes:
                store_data["price_hikes"].append(f"{h.item_name}: wholesale rate ₹{h.unit_wholesale_rate:,.2f}")

    except Exception as exc:
        logger.error(f"Error gathering live store dataset for {clean_merchant}: {exc}", exc_info=True)

    return store_data


def format_dataset_for_llm(data: Dict[str, Any]) -> str:
    """Formats the PostgreSQL store dataset into clear text sections for Gemini."""
    lines = [
        f"STORE: {data['merchant_name']} | DATE: {data['date_str']}",
        "",
        "=== TODAY'S COUNTER INFLOW ===",
        f"Total Inflow: ₹{data['today_sales']['total']:,.2f} ({data['today_sales']['count']} transactions)",
        f"Physical Cash: ₹{data['today_sales']['cash']:,.2f} | UPI / Paytm: ₹{data['today_sales']['upi']:,.2f}",
        "",
        "=== CUSTOMER UDHAAR (KHATA) ===",
        f"Total Outstanding Market Receivables: ₹{data['khata']['total_receivables']:,.2f} across {data['khata']['debtors_count']} debtors",
        f"Credit Given Today: ₹{data['khata']['today_credit_given']:,.2f} | Credit Repaid Today: ₹{data['khata']['today_credit_collected']:,.2f}",
    ]

    if data['khata']['customers']:
        cust_lines = [f"• {c['name']}: ₹{c['balance']:,.2f} baaki" + (f" ({c['phone']})" if c['phone'] else "") for c in data['khata']['customers'][:10]]
        lines.append("Active Debtors:\n" + "\n".join(cust_lines))
    else:
        lines.append("Active Debtors: None (Zero outstanding store credit)")

    lines.append("")
    lines.append("=== SHELF INVENTORY & STOCK ===")
    lines.append(f"Total Working Capital Locked: ₹{data['total_stock_value']:,.2f} across {len(data['inventory'])} batches")
    if data['low_stock_items']:
        lines.append("Low Stock Items (<=5 units): " + ", ".join(data['low_stock_items'][:8]))

    if data['inventory']:
        inv_lines = [
            f"• {item['item_name']}: {item['quantity']} {item['unit']} on shelf | Cost: ₹{item['cost_price']:,.2f} | MRP: ₹{item['retail_mrp']:,.2f} | Margin: ₹{item['unit_margin']:,.2f} ({item['margin_pct']}%)"
            for item in data['inventory'][:15]
        ]
        lines.append("Shelf Items:\n" + "\n".join(inv_lines))
    else:
        lines.append("Shelf Items: Empty (No inventory logged yet)")

    lines.append("")
    lines.append("=== DISTRIBUTOR PAYABLES ===")
    lines.append(f"Total Upcoming Supplier Dues: ₹{data['payables']['total_due']:,.2f} across {len(data['payables']['bills'])} bills")
    if data['payables']['bills']:
        bill_lines = [f"• {b['supplier']}: ₹{b['amount']:,.2f} due on {b['due_date']}" for b in data['payables']['bills'][:6]]
        lines.append("Upcoming Bills:\n" + "\n".join(bill_lines))

    if data['price_hikes']:
        lines.append("\n=== WHOLESALE PRICE HIKES ===\n" + "\n".join(data['price_hikes']))

    return "\n".join(lines)


def enforce_concise_response(text: str, max_words: int = 100) -> str:
    """
    Guarantees the final response adheres strictly to approximately 100 words maximum.
    If the response exceeds max_words, cleanly terminates at the nearest complete sentence
    before or around the limit to maintain readability and grammatical coherence.
    """
    clean_text = text.strip()
    words = clean_text.split()
    if len(words) <= max_words:
        return clean_text

    candidate = " ".join(words[:max_words])
    last_punct = -1
    for p in (".", "!", "?"):
        idx = candidate.rfind(p)
        if idx > last_punct:
            last_punct = idx

    # If clean punctuation found in the latter half, cut at sentence end
    if last_punct > int(len(candidate) * 0.5):
        return candidate[: last_punct + 1].strip()

    # Otherwise return candidate up to max_words
    return candidate.strip() + "..."


def get_deterministic_fallback(store_data: Dict[str, Any], query: str) -> str:
    """
    Direct, concise fallback answer (<100 words) when Gemini API is unreachable.
    Directly answers the user's question using authorized database records.
    """
    q = query.lower()

    # 1. Khata / Udhaar / Debtors / Specific person
    if any(k in q for k in ("khata", "udhaar", "debtor", "debtors", "owe", "owes", "baaki", "credit to", "credit from")):
        for cust in store_data["khata"]["customers"]:
            if cust["name"].lower() in q:
                phone_str = f" Contact: {cust['phone']}." if cust['phone'] else ""
                return enforce_concise_response(
                    f"{cust['name']} has an outstanding Udhaar balance of ₹{cust['balance']:,.2f}.{phone_str}"
                )
        khata = store_data["khata"]
        return enforce_concise_response(
            f"Total outstanding customer Udhaar is ₹{khata['total_receivables']:,.2f} across {khata['debtors_count']} debtors. "
            f"Recommend prioritizing collection from your top debtor to strengthen liquidity."
        )

    # 2. Payables / Supplier / Bills
    if any(k in q for k in ("payable", "payables", "supplier", "distributor", "due", "dues", "bill", "bills", "invoice")):
        pay = store_data["payables"]
        if pay["bills"]:
            top_bill = pay["bills"][0]
            return enforce_concise_response(
                f"Upcoming distributor dues total ₹{pay['total_due']:,.2f} across {len(pay['bills'])} bills. "
                f"Next bill of ₹{top_bill['amount']:,.2f} from {top_bill['supplier']} is due on {top_bill['due_date']}."
            )
        return "You have zero upcoming distributor payables due."

    # 3. Stock / Inventory / Specific item
    if any(k in q for k in ("stock", "inventory", "item", "items", "shelf", "quantity", "batch", "batches", "maal")):
        for item in store_data["inventory"]:
            if item["item_name"].lower() in q:
                return enforce_concise_response(
                    f"{item['item_name']} currently has {item['quantity']} {item['unit']} in stock "
                    f"at a wholesale cost of ₹{item['cost_price']:,.2f} and retail MRP of ₹{item['retail_mrp']:,.2f} "
                    f"(margin of ₹{item['unit_margin']:,.2f} or {item['margin_pct']}%)."
                )

        low_stock_text = f" Low stock warnings: {', '.join(store_data['low_stock_items'][:3])}." if store_data["low_stock_items"] else ""
        return enforce_concise_response(
            f"Your store has {len(store_data['inventory'])} active inventory batches valued at ₹{store_data['total_stock_value']:,.2f}."
            f"{low_stock_text}"
        )

    # 4. Inflow / Cash / Today's sales
    if any(k in q for k in ("cash", "upi", "inflow", "today", "collection", "sale", "sales", "paisa")):
        sales = store_data["today_sales"]
        return enforce_concise_response(
            f"Today's total counter inflow is ₹{sales['total']:,.2f} from {sales['count']} transactions "
            f"(Cash: ₹{sales['cash']:,.2f}, UPI: ₹{sales['upi']:,.2f}). "
            f"Active customer credit given today is ₹{store_data['khata']['today_credit_given']:,.2f} "
            f"with ₹{store_data['khata']['today_credit_collected']:,.2f} collected."
        )

    # 5. General store snapshot
    return enforce_concise_response(
        f"For {store_data['merchant_name']}: Today's inflow is ₹{store_data['today_sales']['total']:,.2f}, "
        f"customer Udhaar receivables total ₹{store_data['khata']['total_receivables']:,.2f}, "
        f"and total shelf stock value is ₹{store_data['total_stock_value']:,.2f} across {len(store_data['inventory'])} batches."
    )


def ask_copilot_llm(merchant_id: str, user_query: str) -> str:
    """
    Universal Gemini Fallback:
    JEv routes questions that existing AI components cannot handle to Gemini.

    Operating flow:
    User question → JEv → Gemini → Authorized database retrieval → Data analysis → Concise answer (~100 words max) → User.
    """
    clean_query = user_query.strip()
    store_data = gather_live_store_dataset(merchant_id=merchant_id)
    dataset_text = format_dataset_for_llm(store_data)

    if settings.GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            system_instruction = (
                "You are the Gemini Fallback AI Copilot for Sahayak retail store management.\n"
                "JEv routes user questions that existing specialized AI components cannot handle to you.\n\n"
                "STRICT OPERATING DIRECTIVES:\n"
                "1. AUTHORIZED DATABASE GROUNDING: Ground your answer strictly in the authenticated merchant's retrieved database records below. Never invent database facts, prices, item names, customer names, transactions, or unverified claims. Never present unsupported assumptions as verified information.\n"
                "2. CONCISE RESPONSE LENGTH (~100 WORDS MAXIMUM): Keep your final response to approximately 100 words maximum. Be direct, concise, and informative.\n"
                "3. HIGH RELEVANCE & FOCUS: Address ONLY the user's specific question and main topic directly in your very first sentence. Avoid unrelated information, lengthy explanations, unnecessary pleasantries or introductions (do NOT say 'Hello', 'As an AI', 'Sure!', or 'Here is the data'), and avoid excessive lists (keep to 2-3 key points if needed).\n"
                "4. EXPLANATIONS, CALCULATIONS & RECOMMENDATIONS: You may create new explanatory sentences, calculate relevant figures (such as net margins, cash balance, recovery percentages, or totals), and provide actionable recommendations based on the retrieved data.\n"
                "5. UNAVAILABLE DATA: If the requested information or item is not in the retrieved database records, explain the limitation briefly in one clear sentence (e.g., 'That item is not recorded in your store inventory records.').\n"
                "6. PRIVACY & SECURITY: Respect merchant identity and RLS isolation. Never expose credentials, API keys, private system details, or another merchant's information.\n"
                "7. FORMAT: Respond directly to the user in clean Markdown."
            )

            prompt = (
                f"=== AUTHORIZED STORE DATABASE RECORDS ===\n"
                f"{dataset_text}\n\n"
                f"User Question: \"{clean_query}\"\n\n"
                "Concise Answer (approx 100 words max):"
            )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=220,
                temperature=0.2,
            )

            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL or "gemini-3.5-flash-lite",
                contents=prompt,
                config=config,
            )

            if resp.text:
                return enforce_concise_response(resp.text.strip(), max_words=100)

        except Exception as e:
            logger.error(f"[CopilotLLM] Gemini generation failed: {e}", exc_info=True)

    # Deterministic fallback if Gemini is unreachable or fails
    return get_deterministic_fallback(store_data=store_data, query=clean_query)

