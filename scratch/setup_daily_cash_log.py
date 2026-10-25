"""
scratch/setup_daily_cash_log.py
Creates daily_cash_logs table in PostgreSQL with RLS, and populates 30 days of
realistic retail inflow/outflow data for merchant 'M_MOHITH_KIE2'.
"""
import sys
import os
from datetime import date, datetime, timedelta
import random

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text, select
from app.db.session import engine, SessionLocal
from app.db.khata_models import DailyCashLog, Base
import app.db.models  # Ensure all models are registered

TARGET_MERCHANT = "M_MOHITH_KIE2"

def setup_and_seed():
    print(f"1. Creating 'daily_cash_logs' table in Supabase PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    print("   Table verified/created successfully!")

    print("2. Configuring PostgreSQL Row-Level Security (RLS)...")
    rls_sql = """
    ALTER TABLE daily_cash_logs ENABLE ROW LEVEL SECURITY;
    DO $$
    BEGIN
        DROP POLICY IF EXISTS merchant_isolation_daily_cash_logs ON daily_cash_logs;
        CREATE POLICY merchant_isolation_daily_cash_logs ON daily_cash_logs
        FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));
    END $$;
    """
    with engine.connect() as conn:
        conn.execute(text(rls_sql))
        conn.commit()
    print("   RLS policy 'merchant_isolation_daily_cash_logs' active!")

    print(f"\n3. Generating 30 days of realistic cash flow logs for merchant: {TARGET_MERCHANT}...")
    today = date.today()
    start_date = today - timedelta(days=29)

    records = []
    current_running_cash = 18500.0  # Starting cash buffer 30 days ago

    # Deterministic seed for reproducible realistic patterns
    random.seed(42)

    for day_offset in range(30):
        log_dt = start_date + timedelta(days=day_offset)
        dow = log_dt.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
        day_of_month = log_dt.day

        # --- INFLOW DYNAMICS ---
        # Baseline sales
        base_sales = random.uniform(3400.0, 4200.0)

        # Day-of-week factor
        if dow in (4, 5, 6):  # Fri, Sat, Sun
            dow_multiplier = random.uniform(1.35, 1.55)
            note_tag = "Weekend grocery rush"
        elif dow == 1:  # Tuesday dip
            dow_multiplier = random.uniform(0.78, 0.88)
            note_tag = "Tuesday mid-week dip"
        else:
            dow_multiplier = random.uniform(0.92, 1.08)
            note_tag = "Regular counter sales"

        # Payday boost (1st-7th of month)
        if 1 <= day_of_month <= 7:
            payday_factor = 1.25
            note_tag += " + Salary week boost"
        else:
            payday_factor = 1.0

        cash_inflow = round(base_sales * dow_multiplier * payday_factor, 2)

        # Khata debt recoveries (Customer Udhaar collections)
        if 1 <= day_of_month <= 7:
            khata_inflow = round(random.uniform(1400.0, 2800.0), 2)
        elif dow in (5, 6):
            khata_inflow = round(random.uniform(600.0, 1200.0), 2)
        else:
            khata_inflow = round(random.uniform(150.0, 500.0), 2)

        total_inflow = round(cash_inflow + khata_inflow, 2)

        # --- OUTFLOW DYNAMICS ---
        # Supplier distributor route visits (Lumpy step drops)
        supplier_outflow = 0.0
        if dow == 1:  # Tuesday: ITC & Packaged goods distributor
            supplier_outflow = round(random.uniform(7500.0, 11500.0), 2)
            note_tag += " | ITC distributor cheque settled"
        elif dow == 4:  # Friday: Edible Oil & Staples supplier
            supplier_outflow = round(random.uniform(6000.0, 9500.0), 2)
            note_tag += " | Oil & Flour delivery settled"

        # Daily operational shop expense (bags, tea, electricity share)
        expense_outflow = round(random.uniform(150.0, 350.0), 2)
        total_outflow = round(supplier_outflow + expense_outflow, 2)

        # Net flow and cumulative closing balance
        net_flow = round(total_inflow - total_outflow, 2)
        current_running_cash = round(current_running_cash + net_flow, 2)

        records.append({
            "merchant_id": TARGET_MERCHANT,
            "log_date": log_dt,
            "cash_inflow": cash_inflow,
            "khata_inflow": khata_inflow,
            "total_inflow": total_inflow,
            "supplier_outflow": supplier_outflow,
            "expense_outflow": expense_outflow,
            "total_outflow": total_outflow,
            "net_flow": net_flow,
            "closing_balance": current_running_cash,
            "notes": note_tag
        })

    with SessionLocal() as session:
        # Delete existing logs for this merchant to ensure clean seed
        session.execute(
            text("DELETE FROM daily_cash_logs WHERE merchant_id = :mid"),
            {"mid": TARGET_MERCHANT}
        )
        for r in records:
            log_entry = DailyCashLog(**r)
            session.add(log_entry)
        session.commit()

    print(f"   Successfully inserted {len(records)} daily cash flow logs for {TARGET_MERCHANT}!")
    print(f"   Date range: {start_date.isoformat()} to {today.isoformat()}")
    print(f"   Final settled closing cash balance: Rs.{current_running_cash:,.2f}")

    # Print sample of the seeded data
    print("\n--- SAMPLE LOGS (FIRST 3 & LAST 3 DAYS) ---")
    with SessionLocal() as session:
        seeded = session.execute(
            select(DailyCashLog)
            .where(DailyCashLog.merchant_id == TARGET_MERCHANT)
            .order_by(DailyCashLog.log_date.asc())
        ).scalars().all()

        for log in seeded[:3] + seeded[-3:]:
            print(f"[{log.log_date} ({log.log_date.strftime('%a')})] "
                  f"Inflow: Rs.{log.total_inflow:,.2f} | Outflow: Rs.{log.total_outflow:,.2f} | "
                  f"Net: {'+' if log.net_flow >= 0 else ''}Rs.{log.net_flow:,.2f} | "
                  f"Closing: Rs.{log.closing_balance:,.2f} | Notes: {log.notes}")

if __name__ == "__main__":
    setup_and_seed()
