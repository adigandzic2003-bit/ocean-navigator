from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0  # stabilere Ergebnisse

def safe_detect(text: str) -> str | None:
    if not text or len(text.strip()) < 40:
        return None
    try:
        return detect(text)
    except Exception:
        return None
