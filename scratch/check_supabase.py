import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from sqlalchemy import text
from app.db.session import engine

def main():
    with engine.connect() as conn:
        res = conn.execute(text("SELECT schema_name FROM information_schema.schemata;")).fetchall()
        print("Schemas:", [r[0] for r in res])

        # Check if auth.users exists
        try:
            users = conn.execute(text("SELECT count(*) FROM auth.users;")).scalar()
            print("Auth users count:", users)
        except Exception as e:
            print("Auth users query error:", e)

if __name__ == "__main__":
    main()
