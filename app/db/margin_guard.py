"""
app/db/margin_guard.py
Agent 3: Deterministic Margin-Guard Price-Shield Engine.
Detects wholesale price increases (>3%) and re-computes recommended retail MRP.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc, func

from app.core.contracts import PriceHikeAlert
from app.db.models import Invoice, InvoiceItem, PriceHistory


def evaluate_price_deviations(
    session: Session,
    merchant_id: str,
    invoice_id: str,
    hike_threshold_pct: float = 3.0,
    target_retail_margin_pct: float = 12.0
) -> List[PriceHikeAlert]:
    """
    Scans all items in the newly saved invoice against historical purchase rates.
    If wholesale cost rose by more than hike_threshold_pct (default 3%),
    generates a PriceHikeAlert with suggested MRP to preserve the merchant's target margin.
    """
    # 0. Fetch invoice header & supplier for alert contextualization
    invoice = session.execute(
        select(Invoice).where(
            and_(
                Invoice.id == invoice_id,
                Invoice.merchant_id == merchant_id
            )
        )
    ).scalars().first()
    supplier_name = invoice.supplier.name if invoice and invoice.supplier else None

    # 1. Fetch current invoice items
    stmt = select(InvoiceItem).where(
        and_(
            InvoiceItem.merchant_id == merchant_id,
            InvoiceItem.invoice_id == invoice_id
        )
    )
    current_items = session.execute(stmt).scalars().all()
    if not current_items:
        return []

    alerts: List[PriceHikeAlert] = []

    # 2. Batch fetch previous wholesale rates in a single query (eliminates N+1 network latency)
    from collections import defaultdict
    cleaned_names = list({item.item_name.strip().lower() for item in current_items})

    rate_stmt = select(
        func.lower(func.trim(PriceHistory.item_name)),
        PriceHistory.unit_wholesale_rate
    ).where(
        and_(
            PriceHistory.merchant_id == merchant_id,
            func.lower(func.trim(PriceHistory.item_name)).in_(cleaned_names)
        )
    ).order_by(desc(PriceHistory.recorded_at), desc(PriceHistory.id))

    raw_history = session.execute(rate_stmt).all()
    history_map = defaultdict(list)
    for name_lower, rate in raw_history:
        if len(history_map[name_lower]) < 2:
            history_map[name_lower].append(rate)

    for item in current_items:
        key = item.item_name.strip().lower()
        rates = history_map.get(key, [])

        # Need at least 2 entries: rates[0] is the current one just added, rates[1] is previous
        if len(rates) >= 2:
            current_rate = rates[0]
            previous_rate = rates[1]

            if previous_rate > 0:
                hike_pct = ((current_rate - previous_rate) / previous_rate) * 100.0

                if hike_pct >= hike_threshold_pct:
                    # Calculate retail prices
                    margin_multiplier = 1.0 + (target_retail_margin_pct / 100.0)
                    previous_mrp = round(previous_rate * margin_multiplier, 2)
                    suggested_new_mrp = round(current_rate * margin_multiplier, 2)
                    estimated_loss = round((current_rate - previous_rate) * item.quantity, 2)
                    rate_diff = round(current_rate - previous_rate, 2)
                    comparison_summary = (
                        f"Wholesale cost rose from ₹{previous_rate:,.2f} to ₹{current_rate:,.2f} "
                        f"(+{hike_pct:.1f}%)."
                    )

                    alert = PriceHikeAlert(
                        merchant_id=merchant_id,
                        item_name=item.item_name,
                        old_wholesale_rate=round(previous_rate, 2),
                        new_wholesale_rate=round(current_rate, 2),
                        percentage_hike=round(hike_pct, 1),
                        previous_mrp=previous_mrp,
                        suggested_new_mrp=suggested_new_mrp,
                        estimated_loss_if_unchanged=estimated_loss,
                        supplier_name=supplier_name,
                        rate_difference=rate_diff,
                        comparison_summary=comparison_summary
                    )
                    alerts.append(alert)

    return alerts


def get_all_price_hikes(
    session: Session,
    merchant_id: str,
    hike_threshold_pct: float = 3.0,
    target_retail_margin_pct: float = 12.0
) -> List[dict]:
    """
    Scans historical purchase records in PriceHistory for a merchant.
    Identifies all SKUs whose latest wholesale cost jumped by >= hike_threshold_pct.
    Calculates recommended shelf MRP to protect gross retail margins (Zero LLM, Pure SQL).
    """
    # 1. Distinct items for this merchant
    item_stmt = select(PriceHistory.item_name).where(
        PriceHistory.merchant_id == merchant_id
    ).distinct()
    items = session.execute(item_stmt).scalars().all()

    hikes: List[dict] = []
    margin_multiplier = 1.0 + (target_retail_margin_pct / 100.0)

    for item_name in items:
        # Get the 2 most recent price recordings for this SKU
        rate_stmt = select(PriceHistory).where(
            and_(
                PriceHistory.merchant_id == merchant_id,
                func.lower(func.trim(PriceHistory.item_name)) == func.lower(func.trim(item_name))
            )
        ).order_by(desc(PriceHistory.recorded_at), desc(PriceHistory.id)).limit(2)

        records = session.execute(rate_stmt).scalars().all()
        if len(records) >= 2:
            current = records[0]
            previous = records[1]
            if previous.unit_wholesale_rate > 0:
                hike_pct = ((current.unit_wholesale_rate - previous.unit_wholesale_rate) / previous.unit_wholesale_rate) * 100.0
                if hike_pct >= hike_threshold_pct:
                    suggested_mrp = round(current.unit_wholesale_rate * margin_multiplier, 2)
                    hikes.append({
                        "item_name": item_name,
                        "old_wholesale_rate": round(previous.unit_wholesale_rate, 2),
                        "new_wholesale_rate": round(current.unit_wholesale_rate, 2),
                        "percentage_hike": round(hike_pct, 1),
                        "suggested_retail_mrp": suggested_mrp,
                        "recorded_at": current.recorded_at
                    })

    # Sort most recent hikes first
    hikes.sort(key=lambda h: h["recorded_at"] or datetime.min, reverse=True)
    return hikes

