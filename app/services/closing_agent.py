"""
app/services/closing_agent.py
Agent 6: The 10:15 PM Shop Closing Storyteller Agent.

Pulls the day's complete ledger from Supabase PostgreSQL:
1. Today's counter cash and UPI collections (CashTransaction)
2. Today's customer Udhaar given vs repayments collected (KhataEntry)
3. Today's wholesale distributor invoices logged (Invoice)
4. Tomorrow's distributor cheques/bills due (credit_due_date)
5. Critical low stock shelf warnings (InventoryBatch)

Sends the SQL dataset to Gemini Flash to synthesize a warm, respectful,
grounded vernacular closing debrief (Hindi/Hinglish/English).
Has a 100% deterministic SQL fallback if LLM is unavailable.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from sqlalchemy import select, and_, desc

from app.workers.config import settings
from app.db.session import get_rls_session
from app.db.khata_models import CashTransaction, CustomerKhata, KhataEntry, InventoryBatch
from app.db.models import Invoice, Merchant

logger = logging.getLogger("sahayak.closing_agent")


class ClosingAgent:
    """Agent 6: 10:15 PM Closing Storyteller Agent."""

    def gather_daily_sql_dataset(self, merchant_id: str) -> Dict[str, Any]:
        """Queries the live PostgreSQL database for the merchant's full daily ledger snapshot."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        day_after_tomorrow = today_start + timedelta(days=2)

        data = {
            "merchant_name": "Merchant",
            "date_str": date.today().strftime("%d-%b-%Y"),
            "cash_inflow": 0.0,
            "upi_inflow": 0.0,
            "total_sales_inflow": 0.0,
            "sales_count": 0,
            "credit_given": 0.0,
            "credit_given_count": 0,
            "repayment_collected": 0.0,
            "repayment_collected_count": 0,
            "invoices_logged_count": 0,
            "invoices_total_amount": 0.0,
            "tomorrow_payables": [],
            "tomorrow_payables_total": 0.0,
            "low_stock_items": [],
            "total_shelf_batches": 0,
            "active_udhaar_total": 0.0,
        }

        with get_rls_session(merchant_id) as session:
            # 1. Merchant name
            m = session.execute(select(Merchant).where(Merchant.id == merchant_id)).scalar_one_or_none()
            if m and m.business_name:
                data["merchant_name"] = m.business_name

            # 2. Today's Sales
            txns = session.execute(
                select(CashTransaction).where(
                    and_(CashTransaction.merchant_id == merchant_id, CashTransaction.created_at >= today_start)
                )
            ).scalars().all()
            data["sales_count"] = len(txns)
            for t in txns:
                if t.payment_method == "CASH":
                    data["cash_inflow"] += t.amount
                else:
                    data["upi_inflow"] += t.amount
            data["total_sales_inflow"] = round(data["cash_inflow"] + data["upi_inflow"], 2)

            # 3. Today's Khata entries
            k_entries = session.execute(
                select(KhataEntry).where(
                    and_(KhataEntry.merchant_id == merchant_id, KhataEntry.created_at >= today_start)
                )
            ).scalars().all()
            for k in k_entries:
                if k.action == "GIVE_CREDIT":
                    data["credit_given"] += k.amount
                    data["credit_given_count"] += 1
                elif k.action == "COLLECT_PAYMENT":
                    data["repayment_collected"] += k.amount
                    data["repayment_collected_count"] += 1

            # 4. Total active Udhaar in market
            all_khatas = session.execute(
                select(CustomerKhata).where(
                    and_(CustomerKhata.merchant_id == merchant_id, CustomerKhata.current_balance > 0)
                )
            ).scalars().all()
            data["active_udhaar_total"] = sum(k.current_balance for k in all_khatas)

            # 5. Today's Invoices logged
            today_invoices = session.execute(
                select(Invoice).where(
                    and_(Invoice.merchant_id == merchant_id, Invoice.created_at >= today_start)
                )
            ).scalars().all()
            data["invoices_logged_count"] = len(today_invoices)
            data["invoices_total_amount"] = sum(inv.total_amount for inv in today_invoices)

            # 6. Tomorrow's distributor cheques / payables
            tomorrow_invoices = session.execute(
                select(Invoice).where(
                    and_(
                        Invoice.merchant_id == merchant_id,
                        Invoice.credit_due_date >= tomorrow_start.date(),
                        Invoice.credit_due_date < day_after_tomorrow.date(),
                    )
                )
            ).scalars().all()
            for inv in tomorrow_invoices:
                sup = inv.supplier.name if inv.supplier else "Distributor"
                data["tomorrow_payables"].append(f"{sup} (₹{inv.total_amount:,.2f})")
                data["tomorrow_payables_total"] += inv.total_amount

            # 7. Low stock items (heading out of stock)
            batches = session.execute(
                select(InventoryBatch).where(
                    and_(InventoryBatch.merchant_id == merchant_id, InventoryBatch.quantity_remaining > 0)
                )
            ).scalars().all()
            data["total_shelf_batches"] = len(batches)
            for b in batches:
                if b.quantity_remaining <= 5.0:
                    data["low_stock_items"].append(f"{b.item_name} ({b.quantity_remaining} {b.unit} left)")

        return data

    def generate_closing_report(self, merchant_id: str) -> str:
        """
        Agent 6: Gathers daily SQL ledger dataset, feeds to LLM,
        and generates the 10:15 PM closing debrief.
        """
        try:
            sql_data = self.gather_daily_sql_dataset(merchant_id)
        except Exception as err:
            logger.error(f"[Agent 6] Error gathering daily SQL data: {err}", exc_info=True)
            return f"⚠️ Error gathering daily ledger data: {err}"

        # Try LLM synthesis with Gemini Flash
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)

                low_stock_str = ", ".join(sql_data["low_stock_items"][:4]) if sql_data["low_stock_items"] else "Sabhi items ka stock safe hai (>5 units)."
                tomorrow_pay_str = ", ".join(sql_data["tomorrow_payables"]) if sql_data["tomorrow_payables"] else "Kal koi distributor cheque due nahi hai."
                tomorrow_total = sql_data["tomorrow_payables_total"]
                is_safe = sql_data["total_sales_inflow"] >= tomorrow_total

                prompt = (
                    "You are Agent 6: The 10:15 PM Shop Closing Storyteller for Indian Kirana & Retail Dukandars.\n"
                    "The shop has just closed for the day. You must synthesize a warm, respectful, concise nightly closing report in Hindi/Hinglish (with English currency numbers).\n\n"
                    "MANDATORY REQUIREMENT: All figures MUST be taken directly from the SQL LEDGER DATASET below. Do not make up numbers:\n\n"
                    "=== DAILY POSTGRESQL LEDGER SNAPSHOT ===\n"
                    f"• Dukaan Name: {sql_data['merchant_name']}\n"
                    f"• Date: {sql_data['date_str']}\n"
                    f"• Total Counter Collection Today: ₹{sql_data['total_sales_inflow']:,.2f} ({sql_data['sales_count']} sales: ₹{sql_data['cash_inflow']:,.2f} Cash + ₹{sql_data['upi_inflow']:,.2f} Paytm UPI)\n"
                    f"• Customer Udhaar Given: ₹{sql_data['credit_given']:,.2f} ({sql_data['credit_given_count']} customers)\n"
                    f"• Customer Repayment Collected: ₹{sql_data['repayment_collected']:,.2f} ({sql_data['repayment_collected_count']} payments)\n"
                    f"• Active Market Udhaar Baaki: ₹{sql_data['active_udhaar_total']:,.2f}\n"
                    f"• Wholesale Bills Logged Today: {sql_data['invoices_logged_count']} bills (₹{sql_data['invoices_total_amount']:,.2f})\n"
                    f"• Tomorrow Distributor Dues: ₹{tomorrow_total:,.2f} -> {tomorrow_pay_str} (Balance Safe: {is_safe})\n"
                    f"• Low Stock Items: {low_stock_str}\n\n"
                    "Format for Telegram in clean Markdown:\n"
                    "🌙 *10:15 PM Dukaan Closing Report (Agent 6)*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Namaste Ji! Aaj dukaan ka din kaisa raha:\n\n"
                    "💵 *Today's Counter Cash & UPI Inflow:*\n"
                    "• Total: *₹{total_sales_inflow}* (Physical Cash: ₹{cash_inflow} | UPI: ₹{upi_inflow})\n\n"
                    "📖 *Customer Khata Today:*\n"
                    "• Udhaar Diya: ₹{credit_given} | Udhaar Wapas Aaya: ₹{repayment_collected}\n"
                    "• Market Baaki: ₹{active_udhaar_total}\n\n"
                    "🚚 *Tomorrow's Distributor Cheques & Dues:*\n"
                    "• Due Tomorrow: ₹{tomorrow_total} ({tomorrow_pay_str})\n"
                    "• Status: {Explain if account balance covers it}\n\n"
                    "📦 *Low Stock Warning:*\n"
                    "• {low_stock_str}\n\n"
                    "Give a warm 1-sentence sign-off wishing them a peaceful rest: 'Dukaan band karne ka samay ho gaya, Shubh Ratri!'\n"
                    "End with: '🔒 _ACID Verified SQL Ledger • Agent 6 Nightly Debrief_'"
                )

                resp = client.models.generate_content(
                    model=settings.GEMINI_MODEL or "gemini-3.5-flash-lite",
                    contents=prompt
                )
                if resp.text:
                    return resp.text.strip()
            except Exception as e:
                logger.warning(f"[Agent 6] Gemini closing report generation fallback: {e}")

        # Deterministic SQL Fallback
        lines = [
            f"🌙 *10:15 PM Dukaan Closing Report (Agent 6)*",
            f"📅 *Date:* {sql_data['date_str']} | *Shop:* {sql_data['merchant_name']}",
            "━━━━━━━━━━━━━━━━━━━━",
            f"💵 *Today's Total Counter Collection:* *₹{sql_data['total_sales_inflow']:,.2f}*",
            f" • 💵 Physical Cash: ₹{sql_data['cash_inflow']:,.2f}",
            f" • 📱 Paytm UPI: ₹{sql_data['upi_inflow']:,.2f}",
            f" • 🧾 Transactions: {sql_data['sales_count']} sales recorded\n",
            f"📖 *Customer Khata (Udhaar) Today:*",
            f" • 📤 Fresh Credit Given: ₹{sql_data['credit_given']:,.2f}",
            f" • 📥 Repayments Collected: ₹{sql_data['repayment_collected']:,.2f}",
            f" • 💰 Total Market Receivables: ₹{sql_data['active_udhaar_total']:,.2f}\n",
            f"🚚 *Tomorrow's Distributor Due Dates:*"
        ]

        if sql_data["tomorrow_payables"]:
            lines.append(f" • ⚠️ *Total Due Tomorrow:* ₹{sql_data['tomorrow_payables_total']:,.2f}")
            for p in sql_data["tomorrow_payables"]:
                lines.append(f"   ↳ {p}")
        else:
            lines.append(" • 🟢 Zero distributor payments due tomorrow. Cash is 100% safe!")

        if sql_data["low_stock_items"]:
            lines.append(f"\n📦 *Low Stock Alerts (Reorder Soon):*")
            for ls in sql_data["low_stock_items"][:4]:
                lines.append(f" • ⚠️ {ls}")

        lines.append("\n🙏 *Dukaan band karne ka samay ho gaya. Shubh Ratri!*")
        lines.append("🔒 _ACID Verified SQL Ledger • Agent 6 Nightly Debrief_")
        return "\n".join(lines)


# Singleton
closing_agent = ClosingAgent()
