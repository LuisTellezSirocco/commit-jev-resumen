"""Evaluate a private collection using a local, untracked expectations file."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jevdocs.core import ROOT, JevClient, save_json
from jevdocs.server import search_documents


def exact_matches(found, expected):
    return all(any(name.startswith(prefix) for name in found) for prefix in expected) and all(
        any(name.startswith(prefix) for prefix in expected) for name in found
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "data/evaluation-cases.json")
    args = parser.parse_args()
    if not args.cases.is_file():
        parser.error(
            "Crea data/evaluation-cases.json siguiendo examples/evaluation-cases.example.json"
        )
    index = json.loads((ROOT / "data/index.json").read_text())
    cases = json.loads(args.cases.read_text())
    out = {
        "scope": "Comprobaciones seleccionadas por el usuario; no miden precisión global.",
        "facets": [],
        "searches": [],
    }
    for prefix, qid, expected in cases.get("checks", []):
        matches = [d for d in index["documents"] if d["filename"].startswith(prefix)]
        if len(matches) != 1:
            parser.error("Cada prefijo de comprobación debe identificar un único documento local")
        doc = matches[0]
        facet = doc["facets"][qid]
        values = (
            [facet["value"]]
            if facet["status"] == "accepted"
            else facet["values"]
            if facet["status"] == "segment_values"
            else []
        )
        out["facets"].append(
            {
                "document": doc["filename"],
                "question": qid,
                "expected": expected,
                "observed": values,
                "status": facet["status"],
                "pass": expected in values,
            }
        )
    client = JevClient()
    try:
        for query, expected in cases.get("queries", []):
            result = search_documents(index, query, client)
            scores = {r["id"]: r["score"] for r in result["results"]}
            found = [d["filename"] for d in index["documents"] if (scores[d["id"]] or 0) >= 0.5]
            possible = [d["filename"] for d in index["documents"] if (scores[d["id"]] or 0) >= 0.25]
            out["searches"].append(
                {
                    "query": query,
                    "expected_prefixes": expected,
                    "found": found,
                    "pass": exact_matches(found, expected),
                    "possible_found": possible,
                    "possible_pass": exact_matches(possible, expected),
                    "result": result,
                }
            )
    finally:
        client.close()
    save_json(ROOT / "output/validacion.json", out)
    lines = ["# Validación de la colección local", "", out["scope"], ""]
    for group, title in [("facets", "Facetas"), ("searches", "Búsquedas")]:
        passed = sum(case["pass"] for case in out[group])
        lines += [f"## {title}: {passed}/{len(out[group])}", ""]
        for case in out[group]:
            description = case.get("query") or f"{case['document']} · {case['question']}"
            observed = case.get("found", case.get("observed"))
            lines.append(f"- {'OK' if case['pass'] else 'REVISAR'} · {description}: {observed}")
        lines.append("")
    possible_passed = sum(c["possible_pass"] for c in out["searches"])
    lines += [
        f"Con umbral de búsqueda ampliado a 0,25: {possible_passed}/{len(out['searches'])}.",
        "",
        "Los umbrales son exploratorios. Se conserva el resultado estándar para no ocultar discrepancias.",
    ]
    (ROOT / "output/validacion.md").write_text("\n".join(lines))
    print(
        "Evaluación terminada. Informes privados en output/validacion.json y output/validacion.md."
    )


if __name__ == "__main__":
    main()
