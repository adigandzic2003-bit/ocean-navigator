import os
from dotenv import load_dotenv
import psycopg2
from typing import Generator

# .env laden, damit DATABASE_URL bekannt ist
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    """Direkter Verbindungshelfer (wird intern genutzt)."""
    return psycopg2.connect(DATABASE_URL)

def get_db() -> Generator:
    """
    FastAPI-Dependency: gibt eine DB-Verbindung weiter und
    schließt sie nach der Anfrage automatisch.
    """
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()
