
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL not found in .env")

    return psycopg2.connect(
        database_url,
        connect_timeout=10
    )
