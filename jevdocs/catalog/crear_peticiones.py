#!/usr/bin/env python3
"""Construye JSON nativo de TypeSafe sin acceder a la red ni enviar documentos.

Python >=3.11, solo biblioteca estándar.
Ejemplo:
  python -m jevdocs.catalog.crear_peticiones --state estado.json --nucleo --salida peticiones
  python -m jevdocs.catalog.crear_peticiones --state estado.json --grupos temas,estructura --salida peticiones

El tamaño de lote es una preferencia de esta herramienta, NO un límite de la API.
Debe comprobarse además el presupuesto de tokens antes de enviar cada petición.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

ROOT = files("jevdocs.catalog")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se puede leer JSON válido de {path}: {exc}") from exc


def validate_state(state: Any) -> None:
    if not isinstance(state, dict) or not isinstance(state.get("document"), dict):
        raise ValueError("state debe ser un objeto con document.")
    document = state["document"]
    extraction = document.get("extraction")
    if not isinstance(extraction, dict):
        raise ValueError("document.extraction debe describir la cobertura y la extracción.")
    if extraction.get("coverage") not in {"full", "partial", "unknown"}:
        raise ValueError("document.extraction.coverage debe ser full, partial o unknown.")
    for flag in ("structure_preserved", "visual_content_described"):
        if not isinstance(extraction.get(flag), bool):
            raise ValueError(f"document.extraction.{flag} debe ser booleano.")
    segments = document.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError(
            "document.segments debe contener segmentos de texto; no clasifiques entradas vacías."
        )
    ids: set[str] = set()
    nonempty = False
    for item in segments:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ValueError("Cada segmento debe ser un objeto con text de tipo string.")
        sid = item.get("id")
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError("Cada segmento debe tener un id string no vacío y único.")
        ids.add(sid)
        text = item["text"].strip()
        nonempty |= bool(text)
        if "SUSTITUIR_POR_" in text:
            raise ValueError(
                "El estado aún contiene el marcador de plantilla; añade contenido real."
            )
    if not nonempty:
        raise ValueError(
            "No hay texto legible para clasificar. Conserva el archivo y marca extracción pendiente."
        )


def select_ids(manifest: dict, groups: list[str] | None = None, core: bool = False) -> list[str]:
    if core or groups is None:
        return list(manifest["nucleo"])
    if groups == []:
        raise ValueError("Selecciona al menos un grupo.")
    if groups == ["todos"]:
        return list(manifest["preguntas"])
    invalid = set(groups) - set(manifest["grupos"])
    if invalid:
        raise ValueError("Grupos desconocidos: " + ", ".join(sorted(invalid)))
    wanted = {qid for group in groups for qid in manifest["grupos"][group]["preguntas"]}
    # Keep stable order and ensure Score gates accompany their dimensions.
    for qid in list(wanted):
        gate = manifest["preguntas"][qid].get("control_aplicabilidad")
        if gate:
            wanted.add(gate)
    return [qid for qid in manifest["preguntas"] if qid in wanted]


def build_requests(
    state: dict, bank: dict, manifest: dict, ids: list[str], model: str, max_questions: int
) -> list[dict]:
    validate_state(state)
    if max_questions < 2:
        raise ValueError("max-preguntas debe ser >=2 para mantener una escala y su control juntos.")
    groups: list[list[str]] = []
    consumed: set[str] = set()
    # Bundle each scale and its applicability check in the same request.
    for qid in ids:
        if qid in consumed:
            continue
        paired_scores = [
            k for k in ids if manifest["preguntas"][k].get("control_aplicabilidad") == qid
        ]
        gate = manifest["preguntas"][qid].get("control_aplicabilidad")
        unit = [gate, qid] if gate else [qid] + paired_scores
        unit = [k for k in unit if k and k not in consumed]
        for key in unit:
            if key not in bank:
                raise ValueError(f"Pregunta inexistente: {key}")
        groups.append(unit)
        consumed.update(unit)
    batches: list[list[str]] = []
    batch: list[str] = []
    for unit in groups:
        if batch and len(batch) + len(unit) > max_questions:
            batches.append(batch)
            batch = []
        batch.extend(unit)
    if batch:
        batches.append(batch)
    return [
        {"model": model, "state": state, "questions": {key: bank[key] for key in batch}}
        for batch in batches
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state", required=True, type=Path, help="JSON del estado con document y extraction."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--nucleo", action="store_true", help="Seleccionar las 49 preguntas del núcleo."
    )
    selector.add_argument("--grupos", help="Grupos separados por comas o todos.")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--max-preguntas", type=int, default=32)
    parser.add_argument("--salida", required=True, type=Path, help="Directorio nuevo o vacío.")
    args = parser.parse_args()
    try:
        bank = load_json(ROOT / "preguntas_jev.json")
        manifest = load_json(ROOT / "catalogo.json")
        state = load_json(args.state)
        groups = [g.strip() for g in args.grupos.split(",") if g.strip()] if args.grupos else None
        ids = select_ids(manifest, groups, args.nucleo)
        requests = build_requests(state, bank, manifest, ids, args.model, args.max_preguntas)
        if args.salida.exists() and (not args.salida.is_dir() or any(args.salida.iterdir())):
            raise ValueError(
                "La salida debe ser un directorio nuevo o vacío; no se sobrescriben archivos."
            )
        args.salida.mkdir(parents=True, exist_ok=True)
        for i, payload in enumerate(requests, 1):
            (args.salida / f"peticion_{i:03d}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(
            f"{len(requests)} peticiones; {len(ids)} preguntas. No se ha enviado contenido a ningún servicio."
        )
        print(
            "Comprueba ambos límites de tokens antes de enviar. No se trunca ni resume el documento automáticamente."
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
