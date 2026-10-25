import time
from sqlalchemy import text
from app.db.session import engine, SessionLocal

t0 = time.perf_counter()
with engine.connect() as conn:
    print(f"Connection 1 acquired in {(time.perf_counter()-t0)*1000:.1f}ms")
    
t1 = time.perf_counter()
with engine.connect() as conn2:
    print(f"Connection 2 (pooled) acquired in {(time.perf_counter()-t1)*1000:.1f}ms")
