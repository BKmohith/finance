"""
init_db.py
Database table creation and Row-Level Security (RLS) setup for Supabase PostgreSQL 16/17.
"""
import sys
import os

# Add finance root to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import text
from app.db.session import engine, Base
import app.db.models  # Registers all models with Base.metadata


def initialize_database():
    print("Connecting to Supabase and creating tables...")
    # 1. Create tables
    Base.metadata.create_all(bind=engine)
    print("All SQLAlchemy tables created successfully!")

    # 2. Configure Row-Level Security (RLS)
    rls_commands = [
        "ALTER TABLE merchants ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE invoice_line_items ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE statutory_audit_log ENABLE ROW LEVEL SECURITY;",
        "ALTER TABLE daily_cash_logs ENABLE ROW LEVEL SECURITY;",

        # Policies
        """
        DO $$
        BEGIN
            DROP POLICY IF EXISTS merchant_isolation_merchants ON merchants;
            CREATE POLICY merchant_isolation_merchants ON merchants
            FOR ALL TO PUBLIC USING (id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_suppliers ON suppliers;
            CREATE POLICY merchant_isolation_suppliers ON suppliers
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_invoices ON invoices;
            CREATE POLICY merchant_isolation_invoices ON invoices
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_items ON invoice_line_items;
            CREATE POLICY merchant_isolation_items ON invoice_line_items
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_prices ON price_history;
            CREATE POLICY merchant_isolation_prices ON price_history
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_audit ON statutory_audit_log;
            CREATE POLICY merchant_isolation_audit ON statutory_audit_log
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));

            DROP POLICY IF EXISTS merchant_isolation_daily_cash ON daily_cash_logs;
            CREATE POLICY merchant_isolation_daily_cash ON daily_cash_logs
            FOR ALL TO PUBLIC USING (merchant_id = current_setting('app.current_merchant_id', true));
        END $$;
        """
    ]

    with engine.connect() as conn:
        for cmd in rls_commands:
            conn.execute(text(cmd))
        conn.commit()
    print("PostgreSQL Row-Level Security (RLS) policies successfully activated!")


if __name__ == "__main__":
    initialize_database()
