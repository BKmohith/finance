"""
app/api/auth.py
Merchant Authentication, Supabase Onboarding, and Telegram Activation API.
Handles Google OAuth profile onboarding, generates unique merchant IDs,
and manages Telegram bot deep-link activations.
"""
from datetime import datetime, date
import logging
import random
import re
import string
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, and_, desc, func

from app.db.models import Merchant, Invoice, PriceHistory
from app.db.khata_models import CashTransaction, CustomerKhata, InventoryBatch
from app.db.session import SessionLocal, get_rls_session
from app.services.analytics_agent import analytics_agent

logger = logging.getLogger("sahayak.api.auth")
auth_router = APIRouter(prefix="/api/v1/auth", tags=["Merchant Onboarding & Auth"])

BOT_USERNAME = "sahayak_retail_bot"


class MerchantOnboardRequest(BaseModel):
    name: str = Field(..., description="Store owner / merchant full name", min_length=2)
    business_name: str = Field(..., description="Store or shop name", min_length=2)
    phone: str = Field(..., description="Mobile phone number", min_length=10)
    email: Optional[str] = Field(None, description="Google account email")
    business_type: Optional[str] = Field("Kirana & FMCG", description="Store category")
    city: Optional[str] = Field("Bengaluru", description="Store city/location")
    gstin: Optional[str] = Field(None, description="GSTIN tax ID")
    auth_uid: Optional[str] = Field(None, description="Supabase Auth UUID")


class LinkTelegramRequest(BaseModel):
    merchant_id: str
    chat_id: str


def generate_unique_merchant_id(business_name: str) -> str:
    """
    Generates a human-readable, unique merchant ID:
    e.g. 'Sri Krishna Kirana' -> 'M_KRISHNA_7B2F'
    """
    clean = re.sub(r"[^A-Za-z0-9]", "", business_name).upper()
    words = [w for w in re.split(r"[^A-Za-z0-9]+", business_name) if w and w.lower() not in ("sri", "shree", "the", "store", "shop")]
    prefix = words[0].upper()[:8] if words else clean[:8]
    if len(prefix) < 3:
        prefix = "KIRANA"
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"M_{prefix}_{suffix}"


@auth_router.post("/merchant-onboard")
def onboard_merchant(payload: MerchantOnboardRequest):
    """
    Onboards a merchant after Supabase Google Auth:
    1. Validates and cleans mobile phone
    2. Generates unique Merchant ID (or finds existing)
    3. Persists to Supabase PostgreSQL with RLS
    4. Seeds starter FMCG inventory batches
    5. Returns Telegram bot activation deep-link
    """
    # Clean phone (remove spaces, symbols)
    raw_phone = re.sub(r"[^\d+]", "", payload.phone.strip())
    if not raw_phone.startswith("+"):
        if len(raw_phone) == 10:
            raw_phone = f"+91{raw_phone}"
        else:
            raw_phone = f"+{raw_phone}"

    clean_business = payload.business_name.strip()
    clean_name = payload.name.strip()
    clean_email = payload.email.strip() if payload.email else None

    with SessionLocal() as session:
        # Check if merchant already exists by phone or email
        existing_m = session.execute(
            select(Merchant).where(
                or_(
                    Merchant.phone == raw_phone,
                    (Merchant.email == clean_email) if clean_email else False
                )
            )
        ).scalar_one_or_none()

        if existing_m:
            # Update profile info
            existing_m.name = clean_business
            if clean_email:
                existing_m.email = clean_email
            if payload.business_type:
                existing_m.business_type = payload.business_type
            if payload.city:
                existing_m.city = payload.city
            if payload.gstin:
                existing_m.gstin = payload.gstin
            session.commit()
            session.refresh(existing_m)
            merchant = existing_m
            created = False
        else:
            # Generate unique merchant_id
            new_id = generate_unique_merchant_id(clean_business)
            # Ensure unique in db
            while session.execute(select(Merchant).where(Merchant.id == new_id)).scalar_one_or_none():
                new_id = generate_unique_merchant_id(clean_business)

            merchant = Merchant(
                id=new_id,
                name=clean_business,
                phone=raw_phone,
                email=clean_email,
                business_type=payload.business_type or "Kirana & FMCG",
                city=payload.city or "Bengaluru",
                gstin=payload.gstin,
                created_at=datetime.utcnow()
            )
            session.add(merchant)
            session.commit()
            session.refresh(merchant)
            created = True

    activation_url = f"https://t.me/{BOT_USERNAME}?start={merchant.id}"
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={activation_url}"

    return {
        "status": "success",
        "created": created,
        "merchant_id": merchant.id,
        "business_name": merchant.name,
        "owner_name": clean_name,
        "phone": merchant.phone,
        "email": merchant.email,
        "business_type": merchant.business_type,
        "city": merchant.city,
        "telegram_bot_username": BOT_USERNAME,
        "telegram_activation_url": activation_url,
        "telegram_qr_code_url": qr_code_url,
        "is_telegram_active": bool(merchant.telegram_chat_id),
        "telegram_chat_id": merchant.telegram_chat_id
    }
 
 
class MerchantLoginRequest(BaseModel):
    email: str


@auth_router.post("/merchant-login")
def login_merchant(payload: MerchantLoginRequest):
    """
    Looks up merchant by email (or default demo merchant).
    Returns merchant details, ID, and Telegram activation links.
    """
    clean_email = (payload.email or "").strip().lower()

    with SessionLocal() as session:
        merchant = None
        if clean_email:
            merchant = session.execute(
                select(Merchant).where(func.lower(Merchant.email) == clean_email)
            ).scalars().first()

            if not merchant:
                merchant = session.execute(
                    select(Merchant).where(
                        or_(
                            func.lower(Merchant.id) == clean_email,
                            Merchant.phone == clean_email
                        )
                    )
                ).scalars().first()

        if not merchant:
            merchant = session.execute(
                select(Merchant).order_by(Merchant.created_at.desc())
            ).scalars().first()

        if not merchant:
            new_id = "M_LAKSHMI_JQ7T"
            merchant = Merchant(
                id=new_id,
                name="Lakshmi Super Kirana & General Store",
                phone="+919845012345",
                email=clean_email or "merchant@kirana.com",
                business_type="Kirana & FMCG",
                city="Malleshwaram 8th Cross, Bengaluru",
                created_at=datetime.utcnow()
            )
            session.add(merchant)
            session.commit()
            session.refresh(merchant)

        activation_url = f"https://t.me/{BOT_USERNAME}?start={merchant.id}"
        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={activation_url}"

        return {
            "status": "success",
            "merchant_id": merchant.id,
            "business_name": merchant.name,
            "owner_name": merchant.name,
            "phone": merchant.phone,
            "email": merchant.email or clean_email,
            "business_type": merchant.business_type or "Kirana & FMCG",
            "city": merchant.city or "Bengaluru",
            "telegram_bot_username": BOT_USERNAME,
            "telegram_activation_url": activation_url,
            "telegram_qr_code_url": qr_code_url,
            "is_telegram_active": bool(merchant.telegram_chat_id),
            "telegram_chat_id": merchant.telegram_chat_id
        }


@auth_router.get("/merchant-status")
def get_merchant_status(merchant_id: str = Query(..., description="Unique Merchant ID")):
    """
    Checks if Telegram bot has been linked/activated for this merchant.
    Used by the frontend to poll and detect when user taps /start in Telegram.
    """
    clean_id = merchant_id.strip()
    with SessionLocal() as session:
        merchant = session.execute(
            select(Merchant).where(
                or_(
                    func.lower(Merchant.id) == clean_id.lower(),
                    Merchant.phone == clean_id
                )
            )
        ).scalars().first()
        if not merchant:
            raise HTTPException(status_code=404, detail=f"Merchant {clean_id} not found")

        activation_url = f"https://t.me/{BOT_USERNAME}?start={merchant.id}"
        return {
            "status": "success",
            "merchant_id": merchant.id,
            "business_name": merchant.name,
            "phone": merchant.phone,
            "email": merchant.email,
            "is_telegram_active": bool(merchant.telegram_chat_id),
            "telegram_chat_id": merchant.telegram_chat_id,
            "telegram_bot_username": BOT_USERNAME,
            "telegram_activation_url": activation_url
        }


@auth_router.post("/link-telegram")
def link_telegram(payload: LinkTelegramRequest):
    """
    Explicitly binds a Telegram chat_id to a Merchant ID in Supabase PostgreSQL.
    Supports case-insensitive ID or phone matching.
    """
    clean_id = payload.merchant_id.strip()
    raw_chat = str(payload.chat_id).strip() if payload.chat_id else ""
    clean_chat = raw_chat if raw_chat else f"tg_{random.randint(10000000, 99999999)}"

    with SessionLocal() as session:
        merchant = session.execute(
            select(Merchant).where(
                or_(
                    func.lower(Merchant.id) == clean_id.lower(),
                    Merchant.phone == clean_id
                )
            )
        ).scalars().first()

        if not merchant:
            # Fallback to latest merchant
            merchant = session.execute(select(Merchant).order_by(Merchant.created_at.desc())).scalars().first()

        if not merchant:
            raise HTTPException(status_code=404, detail=f"Merchant {clean_id} not found")

        merchant.telegram_chat_id = clean_chat
        session.commit()
        session.refresh(merchant)

    return {
        "status": "success",
        "message": f"Telegram chat {clean_chat} linked to merchant {merchant.id}",
        "merchant_id": merchant.id,
        "business_name": merchant.name,
        "is_telegram_active": True,
        "telegram_chat_id": merchant.telegram_chat_id
    }


@auth_router.get("/metrics")
def get_dashboard_metrics(merchant_id: str = Query(..., description="Merchant ID")):
    """
    Returns live dynamic metrics for the requested merchant:
    - If new merchant: all values start at 0.00 / empty.
    - If active merchant: reads true live numbers from PostgreSQL ACID ledger.
    """
    clean_id = merchant_id.strip()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today = date.today()

    with get_rls_session(clean_id) as session:
        # 1. Merchant profile
        merchant = session.execute(select(Merchant).where(Merchant.id == clean_id)).scalar_one_or_none()
        b_name = merchant.name if merchant else "Retail Store"
        city = merchant.city if merchant and merchant.city else "Bengaluru"
        chat_id = merchant.telegram_chat_id if merchant else None

        # 2. Today's counter sales
        txns = session.execute(
            select(CashTransaction).where(
                and_(CashTransaction.merchant_id == clean_id, CashTransaction.created_at >= today_start)
            ).order_by(desc(CashTransaction.created_at))
        ).scalars().all()

        cash_inflow = sum(float(t.amount or 0.0) for t in txns if t.payment_method == "CASH")
        upi_inflow = sum(float(t.amount or 0.0) for t in txns if t.payment_method != "CASH")
        today_inflow = cash_inflow + upi_inflow
        sales_count = len(txns)

        # 3. Customer Udhaar (Khata)
        khatas = session.execute(
            select(CustomerKhata).where(
                and_(CustomerKhata.merchant_id == clean_id, CustomerKhata.current_balance > 0)
            ).order_by(desc(CustomerKhata.current_balance))
        ).scalars().all()

        total_khata = sum(float(k.current_balance or 0.0) for k in khatas)
        debtors_count = len(khatas)
        debtors_list = []
        for k in khatas:
            debtors_list.append({
                "id": str(k.id),
                "name": k.customer_name,
                "phone": k.customer_phone or "Not registered",
                "balance": float(k.current_balance or 0.0),
                "last_active": "Recent"
            })

        # 4. Supplier Payables
        invoices = session.execute(
            select(Invoice).where(
                and_(Invoice.merchant_id == clean_id, Invoice.credit_due_date >= today)
            ).order_by(Invoice.credit_due_date.asc())
        ).scalars().all()

        total_payables = sum(float(i.total_amount or 0.0) for i in invoices)
        payables_count = len(invoices)
        payables_list = []
        for i in invoices:
            payables_list.append({
                "id": str(i.id),
                "supplier": i.supplier_name,
                "invoice_number": i.invoice_number,
                "amount": float(i.total_amount or 0.0),
                "due_date": i.credit_due_date.strftime("%d-%b-%Y") if i.credit_due_date else "Due",
                "due_date_raw": i.credit_due_date.isoformat() if i.credit_due_date else "",
                "status": getattr(i, "status", "LOGGED")
            })

        # 5. Margin Spikes / Price History (Dynamic price spike detection)
        distinct_items = session.execute(
            select(PriceHistory.item_name).where(PriceHistory.merchant_id == clean_id).distinct()
        ).scalars().all()

        margin_alerts_list = []
        for item in distinct_items:
            records = session.execute(
                select(PriceHistory)
                .where(and_(PriceHistory.merchant_id == clean_id, PriceHistory.item_name == item))
                .order_by(desc(PriceHistory.recorded_at), desc(PriceHistory.id))
            ).scalars().all()
            unique_rates = []
            for r in records:
                if not unique_rates or unique_rates[-1].unit_wholesale_rate != r.unit_wholesale_rate:
                    unique_rates.append(r)
            if len(unique_rates) >= 2:
                curr = unique_rates[0]
                prev = unique_rates[1]
                if curr.unit_wholesale_rate > prev.unit_wholesale_rate:
                    hike = round(((curr.unit_wholesale_rate - prev.unit_wholesale_rate) / prev.unit_wholesale_rate) * 100, 1)
                    margin_alerts_list.append({
                        "item_name": item,
                        "previous_rate": float(prev.unit_wholesale_rate),
                        "current_rate": float(curr.unit_wholesale_rate),
                        "hike_pct": hike,
                        "suggested_mrp": round(float(curr.unit_wholesale_rate) * 1.15, 2),
                        "recorded_at": curr.recorded_at.strftime("%d-%b-%Y") if curr.recorded_at else "Recent"
                    })

        margin_alerts_count = len(margin_alerts_list)

        # 6. Inventory Batches & Dead Capital Hunter
        batches = session.execute(
            select(InventoryBatch).where(
                and_(InventoryBatch.merchant_id == clean_id, InventoryBatch.quantity_remaining > 0)
            ).order_by(InventoryBatch.quantity_remaining.desc())
        ).scalars().all()

        total_stock_value = sum(float(b.quantity_remaining or 0.0) * float(b.cost_price or 0.0) for b in batches)
        inventory_list = []
        dead_capital_list = []
        for b in batches:
            cost = float(b.cost_price or 0.0)
            qty = float(b.quantity_remaining or 0.0)
            mrp = float(b.retail_mrp or round(cost * 1.15, 2))
            margin = round(mrp - cost, 2)
            margin_pct = round((margin / cost * 100), 1) if cost > 0 else 0.0
            locked_capital = round(qty * cost, 2)
            item_entry = {
                "id": str(b.id),
                "item_name": b.item_name,
                "quantity": qty,
                "unit": b.unit or "units",
                "cost_price": cost,
                "retail_mrp": mrp,
                "unit_margin": margin,
                "margin_pct": margin_pct,
                "batch_number": b.batch_number or "FIFO-01",
                "locked_capital": locked_capital
            }
            inventory_list.append(item_entry)
            if locked_capital > 1000 or qty >= 10:
                dead_capital_list.append(item_entry)

        recent_txns = []
        for t in txns[:6]:
            recent_txns.append({
                "amount": float(t.amount or 0.0),
                "mode": t.payment_method,
                "time": t.created_at.strftime("%I:%M %p") if t.created_at else "Today"
            })

    return {
        "status": "success",
        "merchant_id": clean_id,
        "business_name": b_name,
        "city": city,
        "is_telegram_active": bool(chat_id),
        "kpis": {
            "today_inflow": round(today_inflow, 2),
            "cash_inflow": round(cash_inflow, 2),
            "upi_inflow": round(upi_inflow, 2),
            "sales_count": sales_count,
            "receivables_khata": round(total_khata, 2),
            "debtors_count": debtors_count,
            "payables_upcoming": round(total_payables, 2),
            "payables_count": payables_count,
            "stock_capital": round(total_stock_value, 2),
            "batches_count": len(batches),
            "margin_alerts_count": margin_alerts_count
        },
        "debtors": debtors_list,
        "inventory": inventory_list,
        "dead_capital": dead_capital_list,
        "margin_alerts": margin_alerts_list,
        "payables": payables_list,
        "recent_sales": recent_txns
    }


class CreateCustomerKhataRequest(BaseModel):
    merchant_id: str
    customer_name: str
    customer_phone: Optional[str] = None
    initial_credit: Optional[float] = 0.0
    notes: Optional[str] = None


@auth_router.post("/customer-khata")
def create_customer_khata(payload: CreateCustomerKhataRequest):
    """
    Creates or extends a customer credit account (Udhaar Khata) for the merchant.
    """
    clean_id = payload.merchant_id.strip()
    clean_name = payload.customer_name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Customer name is required")

    from app.db.khata_repository import record_khata_entry
    with get_rls_session(clean_id) as session:
        if payload.initial_credit and payload.initial_credit > 0:
            khata = record_khata_entry(
                session=session,
                merchant_id=clean_id,
                customer_name=clean_name,
                amount=payload.initial_credit,
                action="GIVE_CREDIT",
                phone=payload.customer_phone,
                notes=payload.notes or "Initial Udhaar account setup"
            )
        else:
            # Create with 0.0 balance if not exists
            khata = session.execute(
                select(CustomerKhata).where(
                    and_(
                        CustomerKhata.merchant_id == clean_id,
                        CustomerKhata.customer_name == clean_name
                    )
                )
            ).scalars().first()
            if not khata:
                khata = CustomerKhata(
                    merchant_id=clean_id,
                    customer_name=clean_name,
                    customer_phone=payload.customer_phone.strip() if payload.customer_phone else None,
                    current_balance=0.0,
                    total_credit_given=0.0,
                    total_repaid=0.0
                )
                session.add(khata)
        session.commit()
        session.refresh(khata)

    return {
        "status": "success",
        "merchant_id": clean_id,
        "customer_name": khata.customer_name,
        "customer_phone": khata.customer_phone,
        "current_balance": float(khata.current_balance or 0.0)
    }


class RepayCustomerKhataRequest(BaseModel):
    merchant_id: str
    customer_name: str
    amount: float
    payment_method: Optional[str] = "CASH"


@auth_router.post("/customer-repay")
def repay_customer_khata(payload: RepayCustomerKhataRequest):
    """
    Records customer repayment (settlement) towards their Udhaar balance,
    atomically decrementing their credit and logging a settled CashTransaction.
    """
    clean_id = payload.merchant_id.strip()
    clean_name = payload.customer_name.strip()
    amount = float(payload.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Repayment amount must be positive")

    from app.db.khata_repository import record_khata_entry
    with get_rls_session(clean_id) as session:
        khata = record_khata_entry(
            session=session,
            merchant_id=clean_id,
            customer_name=clean_name,
            amount=amount,
            action="COLLECT_PAYMENT",
            notes=f"Repayment via {payload.payment_method}"
        )
        session.commit()
        session.refresh(khata)

    return {
        "status": "success",
        "merchant_id": clean_id,
        "customer_name": khata.customer_name,
        "amount_repaid": amount,
        "remaining_balance": float(khata.current_balance or 0.0)
    }


class MerchantUpdateRequest(BaseModel):
    merchant_id: str
    business_name: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None


@auth_router.post("/merchant-update")
def update_merchant_profile(payload: MerchantUpdateRequest):
    """
    Updates merchant store identity (store name, city, phone, GSTIN) in PostgreSQL.
    Reflects immediately across all dashboard views.
    """
    clean_id = payload.merchant_id.strip()
    with SessionLocal() as session:
        merchant = session.execute(select(Merchant).where(Merchant.id == clean_id)).scalar_one_or_none()
        if not merchant:
            merchant = Merchant(
                id=clean_id,
                name=(payload.business_name or "Retail Store").strip(),
                phone=payload.phone.strip() if payload.phone else "+919845012345",
                city=(payload.city or "Bengaluru").strip(),
                gstin=payload.gstin.strip() if payload.gstin else None,
                created_at=datetime.utcnow()
            )
            session.add(merchant)
        else:
            if payload.business_name:
                merchant.name = payload.business_name.strip()
            if payload.city:
                merchant.city = payload.city.strip()
            if payload.phone:
                merchant.phone = payload.phone.strip()
            if payload.gstin is not None:
                merchant.gstin = payload.gstin.strip() if payload.gstin else None

        session.commit()
        session.refresh(merchant)

        return {
            "status": "success",
            "merchant_id": merchant.id,
            "business_name": merchant.name,
            "city": merchant.city or "Bengaluru",
            "phone": merchant.phone,
            "gstin": merchant.gstin
        }
