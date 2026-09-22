"""Install only the official Spanish OCR model in this project's data directory."""

from pathlib import Path

import httpx

path = Path(__file__).resolve().parents[1] / "data/tessdata/spa.traineddata"
if path.exists():
    print("El modelo español ya está instalado.")
else:
    response = httpx.get(
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/spa.traineddata",
        timeout=60,
    )
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    print(f"Modelo español instalado: {path}")
