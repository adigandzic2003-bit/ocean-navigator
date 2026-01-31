import importlib

modules = [
    "fastapi",
    "uvicorn",
    "httpx",
    "trafilatura",
    "bs4",
    "lxml",
    "fitz",          # PyMuPDF
    "langid",
    "sqlalchemy",
    "psycopg2"
]

missing = []

for m in modules:
    try:
        importlib.import_module(m)
    except Exception as e:
        missing.append((m, f"{type(e).__name__}: {e}"))

if not missing:
    print("✅ Alles installiert! Deine Umgebung ist vollständig.")
else:
    print("❌ Fehlende Module oder Importfehler:")
    for name, err in missing:
        print(f"  - {name}: {err}")
