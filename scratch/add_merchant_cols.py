import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from sqlalchemy import text
from app.db.session import engine

def main():
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(64);"))
        conn.execute(text("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS email VARCHAR(128);"))
        conn.execute(text("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS business_type VARCHAR(64);"))
        conn.execute(text("ALTER TABLE merchants ADD COLUMN IF NOT EXISTS city VARCHAR(64);"))
        conn.commit()
        print("Successfully added columns to merchants table!")

        cols = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'merchants';")).fetchall()
        print("Updated merchants columns:", cols)

if __name__ == "__main__":
    main()
