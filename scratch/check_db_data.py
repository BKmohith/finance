"""
scratch/check_db_data.py
Inspects existing inventory batches, invoices, and khatas in Supabase.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.db.khata_models import InventoryBatch, CustomerKhata, CashTransaction
from app.db.models import Invoice, InvoiceItem, PriceHistory, Merchant

def inspect():
    with SessionLocal() as session:
        merchants = session.execute(select(Merchant)).scalars().all()
        print(f"Total Merchants: {len(merchants)}")
        for m in merchants:
            print(f" - Merchant ID: {m.id}, Name: {m.name}")

        batches = session.execute(select(InventoryBatch)).scalars().all()
        print(f"\nTotal Inventory Batches: {len(batches)}")
        for b in batches[:10]:
            margin = (b.retail_mrp - b.cost_price) if b.retail_mrp else 0.0
            margin_pct = (margin / b.retail_mrp * 100) if b.retail_mrp else 0.0
            print(f" - {b.item_name} (Merchant: {b.merchant_id}): Cost=Rs.{b.cost_price}, MRP=Rs.{b.retail_mrp}, Margin=Rs.{margin:.2f} ({margin_pct:.1f}%), Qty={b.quantity_remaining}")

        khatas = session.execute(select(CustomerKhata)).scalars().all()
        print(f"\nTotal Khatas: {len(khatas)}")
        for k in khatas[:5]:
            print(f" - {k.customer_name} (Merchant: {k.merchant_id}): Balance=₹{k.current_balance}")

if __name__ == "__main__":
    inspect()
