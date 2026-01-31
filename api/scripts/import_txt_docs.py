from pathlib import Path

TXT_DIR = Path("data/txt_tests")

for txt_file in TXT_DIR.glob("*.txt"):
    content = txt_file.read_text(encoding="utf-8", errors="ignore")
    print(f"{txt_file.name}: {len(content)} Zeichen")
    print("Vorschau:", content[:200].replace("\n", " "))
