# api/debug_run_analyze_test.py

import os
import psycopg2
import requests
from collections import Counter


# ---------------------------------------------------------------------------
# DB Helpers
# ---------------------------------------------------------------------------

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL ist nicht gesetzt.")
    return psycopg2.connect(db_url)


# ---------------------------------------------------------------------------
# Reset Logic (sauberer Evaluationslauf)
# ---------------------------------------------------------------------------

def reset_kpis_and_docs():
    conn = get_db_connection()
    cur = conn.cursor()

    print("🔄 Lösche alle KPIs ...")
    cur.execute(
        """
        DELETE FROM oin.oin_master
        WHERE record_type = 'kpi';
        """
    )

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


# ---------------------------------------------------------------------------
# Analyze Trigger
# ---------------------------------------------------------------------------

def call_analyze(limit: int = 20):
    url = "http://localhost:8000/analyze/"
    print(f"🚀 Rufe Analyzer auf: POST {url}?limit={limit}")

    try:
        resp = requests.post(url, params={"limit": limit}, timeout=120)
    except Exception as e:
        print(f"❌ Fehler beim Aufruf von /analyze: {e}")
        return None

    print(f"📡 Status: {resp.status_code}")
    print(f"📦 Response: {resp.text}\n")

    if resp.status_code != 200:
        print("❌ Analyze fehlgeschlagen – Abbruch.")
        return None

    return resp


# ---------------------------------------------------------------------------
# KPI Fetch + Evaluation
# ---------------------------------------------------------------------------

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
        ORDER BY created_at DESC;
        """
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("⚠ Keine KPIs gefunden.")
        return

    print(f"\n✅ Gesamtzahl KPIs: {len(rows)}")

    # --- KPI-Key-Verteilung (sehr wichtig für Evaluation) ---
    key_counts = Counter(row[0] for row in rows)

    print("\n📈 KPI-Verteilung nach kpi_key:")
    for key, cnt in key_counts.most_common():
        print(f"  - {key}: {cnt}")

    # --- Detailausgabe (gekürzt) ---
    print("\n🔎 KPI-Details (max. 30 Einträge):")

    for i, row in enumerate(rows[:30], start=1):
        kpi_key, kpi_value, kpi_unit, kpi_context, url = row
        print(f"\n--- KPI #{i} ---")
        print(f"kpi_key   : {kpi_key}")
        print(f"kpi_value : {kpi_value} {kpi_unit or ''}")
        print(f"url       : {url}")
        print(f"context   : {kpi_context[:300]!r}")  # max 300 Zeichen


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== 🔍 KPI-Testlauf (DSR-Evaluationsmodus) ===\n")

    reset_kpis_and_docs()

    resp = call_analyze(limit=20)
    if resp is None:
        return

    fetch_kpis()

    print("\n=== ✅ Testlauf beendet ===")


if __name__ == "__main__":
    main()
