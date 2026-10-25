"""
app/db/fifo_engine.py
Agent 4: Concurrency-Safe FIFO Inventory Depletion Engine.
Domain: Laptop 2 (Developer B) - ACID Financial Core.

Implements PostgreSQL row-level locks (SELECT ... FOR UPDATE) to guarantee:
1. Zero race conditions during peak counter rush hour.
2. Oldest batches (by expiry date and arrival date) are depleted first.
3. Zero negative stock numbers and strict mathematical auditability.
"""
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import and_, func, select
from app.db.khata_models import InventoryBatch

logger = logging.getLogger("sahayak.db.fifo")


def resolve_target_sku(session, merchant_id: str, query_name: str) -> Optional[str]:
    """
    Finds the single best-matching physical SKU in the merchant's inventory.
    Handles vernacular spelling variations (e.g. 'ashirwad', 'aashirvad' -> 'Aashirvaad Atta 10kg').
    """
    import re
    clean = query_name.strip()

    # 1. Exact match check against all merchant SKUs (regardless of stock level)
    exact = session.execute(
        select(InventoryBatch.item_name)
        .where(
            and_(
                InventoryBatch.merchant_id == merchant_id,
                func.lower(func.trim(InventoryBatch.item_name)) == func.lower(clean)
            )
        )
        .limit(1)
    ).scalar()
    if exact:
        return exact

    def normalize(t: str) -> str:
        t = t.lower()
        t = re.sub(r'a+', 'a', t)
        t = t.replace('w', 'v')
        return t

    norm_query_words = re.findall(r'[a-z0-9]{3,}', normalize(clean))
    if not norm_query_words:
        return None

    # 2. Distinct SKUs for merchant
    distinct_skus = session.execute(
        select(InventoryBatch.item_name)
        .where(InventoryBatch.merchant_id == merchant_id)
        .distinct()
    ).scalars().all()

    if not distinct_skus:
        return None

    scored = []
    for sku in distinct_skus:
        norm_sku_words = re.findall(r'[a-z0-9]{3,}', normalize(sku))
        score = sum(
            1 for q in norm_query_words
            if any(q == sw or (len(q) >= 4 and q in sw) or (len(sw) >= 4 and sw in q) for sw in norm_sku_words)
        )
        if score > 0:
            scored.append((score, -len(sku), sku))

    if scored:
        scored.sort(reverse=True)
        return scored[0][2]

    return None


def deplete_inventory_fifo(
    session,
    merchant_id: str,
    item_name: str,
    quantity_to_deplete: float
) -> Dict[str, Any]:
    """
    Executes concurrency-safe FIFO stock batch depletion:
    1. Resolves query to the single best physical SKU.
    2. Locks matching rows with `FOR UPDATE` so concurrent transactions wait.
    3. Sorts batches by earliest expiry date first, then earliest created_at.
    4. Deducts required quantity sequentially across batches.
    
    Returns structured audit report of depleted batches.
    """
    if quantity_to_deplete <= 0:
        raise ValueError("quantity_to_deplete must be greater than zero.")

    clean_name = item_name.strip()
    target_sku = resolve_target_sku(session, merchant_id, clean_name) or clean_name

    # PostgreSQL Row-Level Lock on target SKU:
    batches = session.execute(
        select(InventoryBatch)
        .where(
            and_(
                InventoryBatch.merchant_id == merchant_id,
                func.lower(func.trim(InventoryBatch.item_name)) == func.lower(target_sku),
                InventoryBatch.quantity_remaining > 0
            )
        )
        .order_by(
            InventoryBatch.expiry_date.asc().nulls_last(),
            InventoryBatch.created_at.asc(),
            InventoryBatch.id.asc()
        )
        .with_for_update()
    ).scalars().all()

    depleted_records: List[Dict[str, Any]] = []
    needed = round(quantity_to_deplete, 3)
    total_depleted = 0.0

    for batch in batches:
        if needed <= 0:
            break

        take = min(batch.quantity_remaining, needed)
        take = round(take, 3)
        batch.quantity_remaining = round(batch.quantity_remaining - take, 3)
        needed = round(needed - take, 3)
        total_depleted = round(total_depleted + take, 3)

        depleted_records.append({
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "units_taken": take,
            "cost_price": batch.cost_price,
            "remaining_in_batch": batch.quantity_remaining,
            "expiry_date": str(batch.expiry_date) if batch.expiry_date else None
        })

    if needed > 0:
        logger.warning(
            f"Stock deficit for merchant {merchant_id}, SKU '{clean_name}': "
            f"requested {quantity_to_deplete}, depleted {total_depleted}, short by {needed}"
        )

    session.flush()

    matched_sku_name = batches[0].item_name if batches else clean_name
    unit = batches[0].unit if batches else "units"

    # Calculate remaining shelf stock across all active batches for this SKU
    total_remaining = session.execute(
        select(func.coalesce(func.sum(InventoryBatch.quantity_remaining), 0.0))
        .where(
            and_(
                InventoryBatch.merchant_id == merchant_id,
                func.lower(func.trim(InventoryBatch.item_name)) == func.lower(matched_sku_name),
                InventoryBatch.quantity_remaining > 0
            )
        )
    ).scalar() or 0.0

    return {
        "item_name": clean_name,
        "matched_sku": matched_sku_name,
        "unit": unit,
        "requested_units": quantity_to_deplete,
        "total_depleted": total_depleted,
        "total_remaining": round(float(total_remaining), 3),
        "shortfall": needed,
        "is_fully_fulfilled": needed == 0.0,
        "batches_depleted": depleted_records
    }


def get_stock_availability(
    session,
    merchant_id: str,
    item_name: str
) -> Dict[str, Any]:
    """
    Returns real-time available stock and active batch breakdown for a given SKU.
    """
    clean_name = item_name.strip()
    target_sku = resolve_target_sku(session, merchant_id, clean_name) or clean_name
    batches = session.execute(
        select(InventoryBatch)
        .where(
            and_(
                InventoryBatch.merchant_id == merchant_id,
                func.lower(func.trim(InventoryBatch.item_name)) == func.lower(target_sku),
                InventoryBatch.quantity_remaining > 0
            )
        )
        .order_by(
            InventoryBatch.expiry_date.asc().nulls_last(),
            InventoryBatch.created_at.asc(),
            InventoryBatch.id.asc()
        )
    ).scalars().all()

    if not batches:
        batches = session.execute(
            select(InventoryBatch)
            .where(
                and_(
                    InventoryBatch.merchant_id == merchant_id,
                    InventoryBatch.item_name.ilike(f"%{clean_name}%"),
                    InventoryBatch.quantity_remaining > 0
                )
            )
            .order_by(
                InventoryBatch.expiry_date.asc().nulls_last(),
                InventoryBatch.created_at.asc()
            )
        ).scalars().all()

    if not batches:
        tokens = [w for w in clean_name.split() if len(w) >= 3]
        for token in tokens:
            batches = session.execute(
                select(InventoryBatch)
                .where(
                    and_(
                        InventoryBatch.merchant_id == merchant_id,
                        InventoryBatch.item_name.ilike(f"%{token}%"),
                        InventoryBatch.quantity_remaining > 0
                    )
                )
                .order_by(
                    InventoryBatch.expiry_date.asc().nulls_last(),
                    InventoryBatch.created_at.asc()
                )
            ).scalars().all()
            if batches:
                break

    total_qty = sum(b.quantity_remaining for b in batches)
    earliest_expiry = batches[0].expiry_date if batches and batches[0].expiry_date else None

    return {
        "item_name": clean_name,
        "total_available_units": round(total_qty, 3),
        "batch_count": len(batches),
        "earliest_expiry_date": str(earliest_expiry) if earliest_expiry else None,
        "batches": [
            {
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "quantity_remaining": b.quantity_remaining,
                "cost_price": b.cost_price,
                "expiry_date": str(b.expiry_date) if b.expiry_date else None
            }
            for b in batches
        ]
    }


def restock_inventory_batch(
    session,
    merchant_id: str,
    item_name: str,
    quantity: float,
    cost_price: float,
    batch_number: Optional[str] = None,
    expiry_date: Optional[date] = None,
    retail_mrp: Optional[float] = None,
    unit: str = "units"
) -> InventoryBatch:
    """
    Inserts a newly arrived inventory batch (e.g. from a digitized wholesale invoice).
    """
    if quantity <= 0:
        raise ValueError("Batch quantity must be greater than zero.")
    if cost_price <= 0:
        raise ValueError("Batch cost_price must be greater than zero.")

    batch = InventoryBatch(
        merchant_id=merchant_id,
        item_name=item_name.strip(),
        batch_number=batch_number,
        quantity_initial=round(quantity, 3),
        quantity_remaining=round(quantity, 3),
        cost_price=cost_price,
        retail_mrp=retail_mrp,
        unit=unit,
        expiry_date=expiry_date
    )
    session.add(batch)
    session.flush()
    return batch
