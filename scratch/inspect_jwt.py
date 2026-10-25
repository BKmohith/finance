import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from sqlalchemy import text
from app.db.session import engine

def main():
    with engine.connect() as conn:
        for s in ('auth', 'vault', 'public', 'extensions'):
            try:
                tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s;"), {"s": s}).fetchall()
                print(f"Tables in {s}:", [t[0] for t in tables])
            except Exception as e:
                print(f"Error {s}:", e)

        # Check pg_settings
        settings = conn.execute(text("SELECT name, setting FROM pg_settings WHERE name ILIKE '%jwt%' OR name ILIKE '%secret%' OR name ILIKE '%anon%';")).fetchall()
        print("Settings matching jwt/secret/anon:", settings)

if __name__ == "__main__":
    main()
