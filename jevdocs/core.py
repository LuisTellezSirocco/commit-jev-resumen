from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib.resources import files
from pathlib import Path

import httpx
import pymupdf
from dotenv import load_dotenv

CATALOG = files("jevdocs.catalog")
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PIPELINE_VERSION = "1.0.0"
STATE_BYTES = 19000
REQUEST_BYTES = 55000
INDIVIDUAL_BYTES = 29000


def workspace_root():
    """Private runtime files belong to the working directory, never site-packages."""
    return Path(os.environ.get("JEV_WORKSPACE", Path.cwd())).expanduser().resolve()


def stamp():
    return datetime.now(UTC).isoformat()


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else packed(value).encode()).hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
    temporary.replace(path)


def load_catalog():
    return (
        json.loads((CATALOG / "preguntas_jev.json").read_text(encoding="utf-8")),
        json.loads((CATALOG / "catalogo.json").read_text(encoding="utf-8")),
    )


def compact_text(text):
    return re.sub(
        r"\n{3,}",
        "\n\n",
        "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()),
    ).strip()


def damaged_text(text):
    """Detect common broken PDF character maps without language inference."""
    if len(text.strip()) < 30:
        return True
    controls = sum(0x7F <= ord(c) <= 0x9F or c == "\ufffd" for c in text)
    words = re.findall(r"\b[^\W\d_]{3,}\b", text, re.UNICODE)
    return controls / len(text) > 0.005 or (len(text) > 250 and len(words) < len(text) / 120)


def length_band(words):
    for top, label in [
        (0, "Sin texto"),
        (250, "Muy corto"),
        (1000, "Corto"),
        (5000, "Medio"),
        (20000, "Largo"),
    ]:
        if words <= top:
            return label
    return "Muy largo"


def extract(path: Path, source_root: Path):
    """Extract all pages; OCR text-poor pages when tesseract is installed."""
    content_hash = digest(path.read_bytes())
    pages, warnings = [], []
    with pymupdf.open(path) as pdf:
        if pdf.needs_pass:
            raise ValueError("PDF protegido por contraseña")
        for index, page in enumerate(pdf):
            text = compact_text(page.get_text(sort=True))
            method = "pymupdf"
            original_damaged = damaged_text(text)
            if original_damaged and shutil.which("tesseract"):
                with tempfile.TemporaryDirectory() as temp:
                    image_path = Path(temp) / "page.png"
                    page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).save(image_path)
                    try:
                        spanish = workspace_root() / "data/tessdata/spa.traineddata"
                        lang_args = (
                            ["--tessdata-dir", str(spanish.parent), "-l", "spa"]
                            if spanish.exists()
                            else ["-l", "eng"]
                        )
                        result = subprocess.run(
                            ["tesseract", str(image_path), "stdout", *lang_args],
                            capture_output=True,
                            text=True,
                            timeout=90,
                            check=True,
                        )
                        candidate = compact_text(result.stdout)
                        if len(candidate) < 30:
                            result = subprocess.run(
                                ["tesseract", str(image_path), "stdout", *lang_args, "--psm", "6"],
                                capture_output=True,
                                text=True,
                                timeout=90,
                                check=True,
                            )
                            candidate = compact_text(result.stdout)
                        if candidate and (not damaged_text(candidate) or len(text) < 30):
                            text, method = (
                                candidate,
                                "tesseract-spa" if spanish.exists() else "tesseract-eng",
                            )
                    except (subprocess.SubprocessError, OSError):
                        warnings.append(f"OCR no disponible en página {index + 1}")
            pages.append(
                {
                    "page": index + 1,
                    "text": text,
                    "method": method,
                    "text_quality_suspect": damaged_text(text)
                    or (method.startswith("tesseract") and len(text) < 80),
                    "image_count": len(page.get_images()),
                    "words": len(text.split()),
                }
            )
        thumb = (
            pdf[0].get_pixmap(matrix=pymupdf.Matrix(0.35, 0.35)).tobytes("png") if len(pdf) else b""
        )
        metadata = pdf.metadata
    empty = [p["page"] for p in pages if p["text_quality_suspect"]]
    if empty:
        warnings.append(
            "Páginas sin texto suficiente o con extracción dudosa: " + ", ".join(map(str, empty))
        )
    if any(p["method"].startswith("tesseract") for p in pages):
        warnings.append(
            "Se ha utilizado OCR; revisar cifras, nombres propios y tablas en el PDF original."
        )
    words = sum(p["words"] for p in pages)
    return {
        "id": digest({"path": str(path.relative_to(source_root)), "hash": content_hash})[:16],
        "filename": path.name,
        "relative_path": path.relative_to(source_root).as_posix(),
        "sha256": content_hash,
        "bytes": path.stat().st_size,
        "page_count": len(pages),
        "word_count": words,
        "length_band": length_band(words),
        "pages": pages,
        "extraction": {
            "coverage": "partial" if empty else "full",
            "coverage_meaning": "Cobertura de texto por páginas; las imágenes no se interpretan.",
            "structure_preserved": False,
            "visual_content_described": False,
            "empty_pages": empty,
            "warnings": warnings,
        },
        "pdf_metadata": metadata,
        "thumbnail": "data:image/png;base64," + base64.b64encode(thumb).decode(),
        "extracted_at": stamp(),
    }


def split_utf8(text, limit):
    """No discarded text, even for enormous paragraphs or multibyte characters."""
    while text:
        raw = text.encode()
        prefix = raw[:limit].decode("utf-8", errors="ignore")
        if len(raw) > limit:
            boundary = prefix.rfind("\n")
            if boundary > len(prefix) // 2:
                prefix = prefix[: boundary + 1]
        if not prefix:
            raise ValueError("Presupuesto de fragmento insuficiente")
        yield prefix
        text = text[len(prefix) :]


def make_units(doc):
    segments, current, size = [], [], 0
    for page in doc["pages"]:
        for part, text in enumerate(split_utf8(page["text"], STATE_BYTES - 1500)):
            segment = {"id": f"p{page['page']:04d}_{part:03d}", "page": page["page"], "text": text}
            length = len(packed(segment).encode())
            if current and size + length > STATE_BYTES:
                segments.append(current)
                current, size = [], 0
            current.append(segment)
            size += length
    if current:
        segments.append(current)
    return [
        {
            "id": f"u{i + 1:03d}",
            "pages": sorted({s["page"] for s in segs}),
            "state": {
                "document": {
                    "extraction": {
                        **doc["extraction"],
                        "coverage": doc["extraction"]["coverage"]
                        if len(segments) == 1
                        else "partial",
                        "unit": i + 1,
                        "total_units": len(segments),
                    },
                    "segments": segs,
                }
            },
        }
        for i, segs in enumerate(segments)
    ]


def batch_questions(state, bank, model):
    current = {}
    for qid, question in bank.items():
        if len(packed({"state": state, "question": question}).encode()) > INDIVIDUAL_BYTES:
            raise ValueError(f"El estado y la pregunta {qid} exceden el presupuesto conservador")
        proposed = {**current, qid: question}
        if (
            len(packed({"model": model, "state": state, "questions": proposed}).encode())
            > REQUEST_BYTES
        ):
            if not current:
                raise ValueError("Pregunta demasiado grande")
            yield current
            current = {}
        current[qid] = question
    if current:
        yield current


def number(value, low, high):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and low <= value <= high
    )


def validate_response(response, questions):
    if not isinstance(response, dict) or not isinstance(response.get("model"), str):
        raise ValueError("Respuesta sin modelo")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Respuesta incompleta o con IDs inesperados")
    for qid, q in questions.items():
        a = answers[qid]
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            raise ValueError(f"Tipo inválido: {qid}")
        if q["type"] == "noul":
            if not number(a.get("noul"), 0, 1):
                raise ValueError(f"Noul inválido: {qid}")
            continue
        if not number(a.get("confidence"), 0, 1):
            raise ValueError(f"Confianza inválida: {qid}")
        keys = (
            set(q["criteria"])
            if q["type"] == "choice"
            else {str(i) for i in range(len(q["criteria"]))}
        )
        probabilities = a.get("probabilities", {})
        if (
            not isinstance(probabilities, dict)
            or not probabilities
            or not set(probabilities) <= keys
            or not all(number(v, 0, 1) for v in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > 0.025
        ):
            raise ValueError(f"Distribución inválida: {qid}")
        if q["type"] == "choice" and a.get("choice") not in keys:
            raise ValueError(f"Opción inválida: {qid}")
        if q["type"] == "score" and not number(a.get("score"), 0, len(q["criteria"]) - 1):
            raise ValueError(f"Puntuación inválida: {qid}")


class JevClient:
    def __init__(self, cache_dir=None, model=None, transport=None):
        load_dotenv(workspace_root() / ".env")
        self.key = os.environ.get("JEV_API_KEY", "")
        self.model = model or os.environ.get("JEV_MODEL", "jev-1.13.0")
        self.cache_dir = Path(cache_dir or workspace_root() / "data/cache")
        self.http = httpx.Client(timeout=120, transport=transport, follow_redirects=False)

    def close(self):
        self.http.close()

    def decide(self, state, questions):
        payload = {"model": self.model, "state": state, "questions": questions}
        request_hash = digest(
            {"endpoint": ENDPOINT, "pipeline": PIPELINE_VERSION, "payload": payload}
        )
        path = self.cache_dir / f"{request_hash}.json"
        if path.exists():
            record = json.loads(path.read_text())
            validate_response(record["response"], questions)
            return {**record, "cached": True}
        if not self.key:
            raise RuntimeError("Falta JEV_API_KEY en .env")
        started = time.monotonic()
        for attempt in range(4):
            try:
                r = self.http.post(
                    ENDPOINT, headers={"Authorization": f"Bearer {self.key}"}, json=payload
                )
            except httpx.TransportError:
                if attempt == 3:
                    raise RuntimeError("No se pudo conectar con JEV") from None
                time.sleep(2**attempt)
                continue
            if r.status_code in (429, 500, 502, 503, 504, 529) and attempt < 3:
                delay = 2**attempt
                retry = r.headers.get("retry-after")
                if retry:
                    try:
                        delay = max(delay, float(retry))
                    except ValueError:
                        try:
                            delay = max(
                                delay,
                                (parsedate_to_datetime(retry) - datetime.now(UTC)).total_seconds(),
                            )
                        except (ValueError, TypeError):
                            pass
                time.sleep(min(delay, 60))
                continue
            if not r.is_success:
                raise RuntimeError(
                    f"JEV HTTP {r.status_code}; revisa clave, saldo o límites. No se registra el cuerpo por privacidad."
                )
            response = r.json()
            validate_response(response, questions)
            record = {
                "request_hash": request_hash,
                "created_at": stamp(),
                "request": payload,
                "response": response,
                "seconds": round(time.monotonic() - started, 3),
            }
            save_json(path, record)
            return {**record, "cached": False}
        raise RuntimeError("Reintentos agotados")


def aggregate(doc, bank, manifest, threshold=0.7):
    """Keep per-unit decisions; never average topics, types or scores."""
    output = {}
    for qid, q in bank.items():
        observations = []
        for unit in doc["units"]:
            a = unit.get("answers", {}).get(qid)
            if not a:
                continue
            value = a.get("choice", a.get("score"))
            confidence = a["confidence"]
            status = "accepted" if confidence >= threshold else "review_required"
            if q["type"] == "score":
                gate = unit.get("answers", {}).get(
                    manifest["preguntas"][qid]["control_aplicabilidad"]
                )
                if not gate or gate["confidence"] < threshold:
                    status = "applicability_unresolved"
                elif gate["choice"] == "no_aplica":
                    status = "not_applicable"
                elif gate["choice"] != "evaluable":
                    status = "insufficient_evidence"
            observations.append(
                {
                    "unit": unit["id"],
                    "pages": unit["pages"],
                    "value": value,
                    "confidence": confidence,
                    "status": status,
                    "raw": a,
                }
            )
        accepted = [o for o in observations if o["status"] == "accepted"]
        values = list(dict.fromkeys(o["value"] for o in accepted))
        complete = len(observations) == len(doc["units"]) and bool(doc["units"])
        status = "not_evaluated" if not observations else "review_required"
        value = None
        scope = "document" if len(doc["units"]) == 1 else "segments"
        if q["type"] == "score":
            if accepted:
                value = accepted[0]["value"] if len(doc["units"]) == 1 else None
                status = "accepted" if len(doc["units"]) == 1 else "segment_values"
            elif observations and all(o["status"] == "not_applicable" for o in observations):
                status = "not_applicable"
        elif "presente" in q["criteria"] and "presente" in values:
            value, status = "presente", "accepted"
        elif manifest["preguntas"][qid]["grupo"] == "temas":
            positive = [v for v in ("central", "secundario", "mencion") if v in values]
            if positive:
                value, status = positive[0], "accepted"
        if value is None and q["type"] != "score":
            if complete and len(accepted) == len(doc["units"]) and len(values) == 1:
                value, status = values[0], "accepted"
                if value == "no_observado" and doc["extraction"]["coverage"] != "full":
                    value, status = None, "insufficient_evidence"
            elif len(values) > 1:
                status = "conflicting"
            elif qid == "tipo_documental" and accepted and len(doc["units"]) > 1:
                # A local accepted type is searchable, explicitly scoped to segments.
                status = "segment_values"
        output[qid] = {
            "value": value,
            "status": status,
            "scope": scope,
            "values": values,
            "observations": observations,
        }
    return output
