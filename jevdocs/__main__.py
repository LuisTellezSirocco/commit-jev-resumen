from __future__ import annotations

import argparse
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .core import (
    PIPELINE_VERSION,
    ROOT,
    JevClient,
    aggregate,
    batch_questions,
    digest,
    extract,
    load_catalog,
    make_units,
    packed,
    save_json,
    stamp,
)


def build(index, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    bank, manifest = load_catalog()
    data = {**index, "questions": bank, "catalog": manifest}
    # Escape script terminators and HTML characters in embedded document text.
    serialized = (
        packed(data).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    )
    html = (ROOT / "web/index.html").read_text()
    html = html.replace("/* APP_CSS */", (ROOT / "web/style.css").read_text())
    html = html.replace("/* APP_JS */", (ROOT / "web/app.js").read_text())
    html = html.replace("/* DATA_JSON */", serialized)
    (output / "index.html").write_text(html)
    save_json(output / "index.json", data)
    for doc in index["documents"]:
        src = Path(index["source_dir"]) / doc["relative_path"]
        target = output / "originals" / doc["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    report(index, bank, manifest, output)


def report(index, bank, manifest, output):
    docs = index["documents"]
    lines = [
        "# Resultados de la clasificación real con JEV",
        "",
        f"Generado: {index['created_at']}. Modelo: {', '.join(index['models'])}.",
        "",
        f"{len(docs)} documentos; {sum(d['page_count'] for d in docs)} páginas; "
        f"{sum(d['word_count'] for d in docs):,} palabras extraídas. Catálogo de {len(bank)} preguntas.",
        "",
        f"{index['run']['requests']} peticiones de clasificación, {index['run']['input_tokens']:,} tokens de entrada "
        f"y {index['run']['output_tokens']:,} de salida (incluye peticiones recuperadas de caché).",
        "",
        "## Interpretación",
        "",
        "Las fichas son composiciones de etiquetas cerradas y extractos literales. No son resúmenes generados por un LLM. "
        "El umbral exploratorio de confianza es 0,70: no está calibrado y no demuestra exactitud. "
        "Los resultados dudosos, conflictos y respuestas no aplicables se conservan. Las escalas de fragmentos no se promedian.",
        "",
        "Las páginas indicadas delimitan la unidad examinada por JEV, no una cita probatoria localizada por el modelo. "
        "Para comprobar una etiqueta, abre el texto o PDF. La relevancia central en un fragmento no implica centralidad global.",
        "",
    ]
    for doc in docs:
        lines += [
            f"## {doc['filename']}",
            "",
            f"{doc['page_count']} páginas · {doc['word_count']} palabras · {len(doc['units'])} unidades · SHA-256 `{doc['sha256']}`",
            "",
        ]
        for key in [
            "tipo_documental",
            "finalidad_principal",
            "idioma_principal",
            "audiencia_principal",
        ]:
            facet = doc["facets"][key]
            display = facet["value"] or (
                ", ".join(map(str, facet["values"])) + " (en fragmentos)"
                if facet["status"] == "segment_values"
                else facet["status"]
            )
            lines.append(f"- **{manifest['preguntas'][key]['etiqueta_ui']}**: {display}")
        topics = [
            manifest["preguntas"][k]["etiqueta_ui"] + " (" + f["value"] + ")"
            for k, f in doc["facets"].items()
            if k.startswith("tema_") and f["value"] in ("central", "secundario", "mencion")
        ]
        lines += ["", "**Temas observados:** " + "; ".join(topics), "", "**Contenido detectado:**"]
        lines += [
            "- " + manifest["preguntas"][k]["etiqueta_ui"]
            for k, f in doc["facets"].items()
            if f["value"] == "presente"
        ]
        lines += [
            "",
            "**Extracción:** "
            + ("; ".join(doc["extraction"]["warnings"]) or "Texto extraído de todas las páginas."),
            "",
        ]
        lines += [
            "**Pendiente de revisión:** "
            + str(
                sum(
                    f["status"] not in ("accepted", "not_applicable", "segment_values")
                    for f in doc["facets"].values()
                )
            )
            + " facetas.",
            "",
        ]
        if doc.get("errors"):
            lines += ["**Errores:** " + "; ".join(doc["errors"]), ""]
    lines += [
        "## Fuentes técnicas",
        "",
        "- https://docs.typesafe.ai/api",
        "- https://docs.typesafe.ai/models",
        "- https://docs.typesafe.ai/confidence",
        "",
    ]
    (output / "informe.md").write_text("\n".join(lines))


def classify(args):
    bank, manifest = load_catalog()
    if args.profile == "core":
        selected = set(manifest["nucleo"]) | set(manifest["grupos"]["temas"]["preguntas"])
        selected_bank = {k: v for k, v in bank.items() if k in selected}
    else:
        selected_bank = bank
    source = Path(args.docs).resolve()
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if not files:
        raise SystemExit(f"No hay PDF en {source}")
    if args.limit:
        files = files[: args.limit]
    client = JevClient(model=args.model)
    started = time.monotonic()
    documents, errors, tasks = [], [], []
    for path in files:
        print(f"Extrayendo {path.name}", flush=True)
        try:
            doc = extract(path, source)
        except Exception as error:
            errors.append({"file": path.name, "error": type(error).__name__})
            continue
        doc["units"] = make_units(doc)
        doc["errors"] = []
        for unit in doc["units"]:
            unit["answers"], unit["requests"] = {}, []
            for batch in batch_questions(unit["state"], selected_bank, client.model):
                tasks.append((doc, unit, batch))
        documents.append(doc)
    print(
        f"{len(documents)} documentos, {sum(len(d['units']) for d in documents)} unidades, {len(tasks)} peticiones.",
        flush=True,
    )
    if args.dry_run:
        client.close()
        print("Solo extracción y planificación: no se ha llamado a JEV.")
        return
    usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0, "cached": 0}
    models = set()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(client.decide, unit["state"], batch): (doc, unit, batch)
                for doc, unit, batch in tasks
            }
            for n, future in enumerate(as_completed(futures), 1):
                doc, unit, batch = futures[future]
                try:
                    record = future.result()
                    response = record["response"]
                    unit["answers"].update(response["answers"])
                    unit["requests"].append(
                        {k: record[k] for k in ("request_hash", "created_at", "seconds", "cached")}
                    )
                    models.add(response["model"])
                    usage["requests"] += 1
                    usage["cached"] += int(record["cached"])
                    for key in ("input_tokens", "output_tokens"):
                        usage[key] += response.get("usage", {}).get(key, 0)
                    print(
                        f"[{n}/{len(tasks)}] {doc['filename']} / {unit['id']}: {len(batch)} respuestas"
                        + (" (caché)" if record["cached"] else ""),
                        flush=True,
                    )
                except Exception as error:
                    msg = f"{unit['id']}: {error}"
                    doc["errors"].append(msg)
                    print(f"[{n}/{len(tasks)}] ERROR {doc['filename']}: {msg}", flush=True)
    finally:
        client.close()
    for doc in documents:
        doc["facets"] = aggregate(doc, bank, manifest)
        doc["status"] = "complete" if doc["units"] and not doc["errors"] else "incomplete"
        save_json(ROOT / "data/documents" / f"{doc['id']}.json", doc)
    index = {
        "created_at": stamp(),
        "pipeline_version": PIPELINE_VERSION,
        "catalog_version": manifest["version_catalogo"],
        "catalog_hash": digest(bank),
        "models": sorted(models),
        "source_dir": str(source),
        "profile": args.profile,
        "policy": {"threshold": 0.7, "calibrated": False},
        "documents": documents,
        "extraction_errors": errors,
        "run": {**usage, "seconds": round(time.monotonic() - started, 2)},
    }
    save_json(ROOT / "data/index.json", index)
    build(index, args.output)
    print(f"HTML generado: {Path(args.output).resolve() / 'index.html'}", flush=True)
    if errors or any(d["status"] == "incomplete" for d in documents):
        raise SystemExit(
            "Clasificación parcial. Los errores figuran en el índice; vuelve a ejecutar para reintentar."
        )


def main():
    parser = argparse.ArgumentParser(description="Clasificación documental y explorador JEV")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("classify")
    p.add_argument("--docs", default=str(ROOT / "docs"))
    p.add_argument("--output", default=str(ROOT / "output"))
    p.add_argument("--profile", choices=["full", "core"], default="full")
    p.add_argument("--model")
    p.add_argument("--workers", type=int, choices=range(1, 9), default=3)
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")
    p = commands.add_parser("build")
    p.add_argument("--output", default=str(ROOT / "output"))
    p = commands.add_parser("serve")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--output", default=str(ROOT / "output"))
    args = parser.parse_args()
    if args.command == "classify":
        classify(args)
    elif args.command == "build":
        build(json.loads((ROOT / "data/index.json").read_text()), args.output)
    else:
        from .server import serve

        serve(Path(args.output), args.port)


if __name__ == "__main__":
    main()
