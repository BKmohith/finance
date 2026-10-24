"""
app/db/margin_guard.py
Agent 3: Deterministic Margin-Guard Price-Shield Engine.
Detects wholesale price increases (>3%) and re-computes recommended retail MRP.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc

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
    # 1. Fetch current invoice items
    stmt = select(InvoiceItem).where(
        and_(
            InvoiceItem.merchant_id == merchant_id,
            InvoiceItem.invoice_id == invoice_id
        )
    )
    current_items = session.execute(stmt).scalars().all()
    alerts: List[PriceHikeAlert] = []

    for item in current_items:
        # 2. Look up the previous wholesale rate for this item
        # We order by recorded_at descending and get the previous entry
        rate_stmt = select(PriceHistory.unit_wholesale_rate).where(
            and_(
                PriceHistory.merchant_id == merchant_id,
                PriceHistory.item_name == item.item_name
            )
        ).order_by(desc(PriceHistory.recorded_at)).limit(2)

        rates = session.execute(rate_stmt).scalars().all()

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

                    alert = PriceHikeAlert(
                        merchant_id=merchant_id,
                        item_name=item.item_name,
                        old_wholesale_rate=round(previous_rate, 2),
                        new_wholesale_rate=round(current_rate, 2),
                        percentage_hike=round(hike_pct, 1),
                        previous_mrp=previous_mrp,
                        suggested_new_mrp=suggested_new_mrp,
                        estimated_loss_if_unchanged=estimated_loss
                    )
                    alerts.append(alert)

    return alerts
