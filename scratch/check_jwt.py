import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from sqlalchemy import text
from app.db.session import engine

def main():
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'auth';")).fetchall()
        print("Auth tables:", [t[0] for t in tables])

if __name__ == "__main__":
    main()
