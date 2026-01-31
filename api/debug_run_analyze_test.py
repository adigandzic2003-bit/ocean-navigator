# api/debug_run_analyze_test.py

import os
import psycopg2
import requests


def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL ist nicht gesetzt.")
    return psycopg2.connect(db_url)


def reset_kpis_and_docs():
    conn = get_db_connection()
    cur = conn.cursor()

    print("🔄 Lösche alte KPIs ...")
    cur.execute("DELETE FROM oin.oin_master WHERE record_type = 'kpi';")

    print("🔄 Setze alle DOCs auf status='new' ...")
    cur.execute(
        """
        UPDATE oin.oin_master
        SET status = 'new'
        WHERE record_type = 'doc';
        """
    )

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Reset fertig.\n")


def call_analyze(limit: int = 10):
    url = "http://localhost:8000/analyze/"
    print(f"🚀 Rufe Analyzer auf: POST {url}?limit={limit}")

    try:
        resp = requests.post(url, params={"limit": limit}, timeout=60)
    except Exception as e:
        print(f"❌ Fehler beim Aufruf von /analyze: {e}")
        return None

    print(f"📡 Status: {resp.status_code}")
    print(f"📦 Response: {resp.text}\n")
    return resp


def fetch_kpis():
    conn = get_db_connection()
    cur = conn.cursor()

    print("📊 Lese neue KPIs aus der DB ...")
    cur.execute(
        """
        SELECT
            kpi_key,
            kpi_value,
            kpi_unit,
            kpi_context,
            extracted_from_url
        FROM oin.oin_master
        WHERE record_type = 'kpi'
        ORDER BY created_at DESC
        LIMIT 200;
        """
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("⚠ Keine KPIs gefunden.")
        return

    for i, row in enumerate(rows, start=1):
        kpi_key, kpi_value, kpi_unit, kpi_context, url = row
        print(f"\n--- KPI #{i} ---")
        print(f"kpi_key   : {kpi_key}")
        print(f"kpi_value : {kpi_value} {kpi_unit or ''}")
        print(f"url       : {url}")
        print(f"context   : {kpi_context[:300]!r}")  # nur die ersten 300 Zeichen


def main():
    print("=== 🔍 KPI-Testlauf (alle Detektoren) starten ===\n")

    reset_kpis_and_docs()
    call_analyze(limit=20)
    fetch_kpis()

    print("\n=== ✅ Testlauf beendet ===")


if __name__ == "__main__":
    main()
