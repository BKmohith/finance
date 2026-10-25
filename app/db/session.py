"""
app/db/session.py
Database engine and session management with PostgreSQL Row-Level Security (RLS) scoping.
"""
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DATABASE_URL

# Create SQLAlchemy engine with connection pool
db_url = DATABASE_URL
try:
    import psycopg  # noqa: F401
except ImportError:
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(
    db_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300
)

# Standard session factory (expire_on_commit=False prevents DetachedInstanceError on model reads)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

# Declarative base for ORM models
Base = declarative_base()


@contextmanager
def get_rls_session(merchant_id: str):
    """
    Session context manager that scopes database access strictly to a single merchant_id
    using PostgreSQL session parameters for Row-Level Security (RLS).
    
    In Supabase, switching to the 'authenticated' role enforces RLS policies
    while current_setting('app.current_merchant_id') isolates tenant data.
    """
    session = SessionLocal()
    try:
        # Switch to non-bypass role and set session merchant identity (split for psycopg 3 prepared statement support)
        session.execute(text("SET LOCAL ROLE authenticated;"))
        session.execute(
            text("SELECT set_config('app.current_merchant_id', :m_id, true);"),
            {"m_id": merchant_id}
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_admin_session():
    """
    Administrative session for migrations, schema generation, or tenant provisioning.
    Bypasses tenant-specific RLS.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
