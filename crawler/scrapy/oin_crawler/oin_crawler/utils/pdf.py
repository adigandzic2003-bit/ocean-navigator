import fitz  # PyMuPDF

def extract_pdf_text(bytes_data: bytes) -> str:
    doc = fitz.open(stream=bytes_data, filetype="pdf")
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
    return "\n".join(parts)
