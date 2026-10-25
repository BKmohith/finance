import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models import Merchant

with SessionLocal() as s:
    m = s.execute(select(Merchant).where(Merchant.id == "M_MOHITH_KIE2")).scalar_one_or_none()
    if m:
        print(f"ID: {m.id}, Name: {m.name}, City: {m.city}, BusinessType: {m.business_type}")
        if not m.city:
            m.city = "Bangalore, Karnataka"
            m.business_type = "Kirana & FMCG Retail Store"
            s.commit()
            print(f"Updated city to: {m.city}")
    else:
        print("Merchant not found")
