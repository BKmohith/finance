"""
app/db/session.py
Database engine and session management with PostgreSQL Row-Level Security (RLS) scoping.
"""
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DATABASE_URL

# Create SQLAlchemy engine with connection pool
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300
)

# Standard session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
        # Switch to non-bypass role so RLS is strictly enforced
        session.execute(text("SET LOCAL ROLE authenticated;"))
        # Set session-scoped merchant identity (transaction-local)
        session.execute(
            text("SELECT set_config('app.current_merchant_id', :m_id, true)"),
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
