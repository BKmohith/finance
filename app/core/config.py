import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.qhuzerpsnkxmbjrkaadz:Mohithbk%402007@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
)
