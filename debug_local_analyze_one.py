import os
import psycopg2

# IMPORTANT: now this import works because we are in project root
from api.analyzer.kpi_analyzer import analyze_document_row

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        select id, extracted_from_url, raw_text, status
        from oin.oin_master
        where record_type='doc'
        order by created_at desc
        limit 1
    """)
    row = cur.fetchone()

    if not row:
        print("❌ No DOC found")
        return

    doc_id, url, raw_text, status = row
    print("DOC:", doc_id, status, url)
    print("raw_len:", len(raw_text or ""))
    print("raw_head:", (raw_text or "")[:300].replace("\n", " "))

    kpis = analyze_document_row({
        "id": doc_id,
        "extracted_from_url": url,
        "raw_text": raw_text,
        "status": status
    })

    print("\nKPIs returned:", 0 if not kpis else len(kpis))
    if kpis:
        for i, k in enumerate(kpis[:20], 1):
            print(f"\n--- KPI {i} ---")
            for kk, vv in k.items():
                print(f"{kk}: {vv}")

if __name__ == "__main__":
    main()
PY
