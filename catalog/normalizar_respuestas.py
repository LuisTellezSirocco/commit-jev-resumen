"""Convierte respuestas API en facetas sin inventar predicciones ni umbrales universales.

Usar después de fusionar por ID las respuestas de peticiones sobre la MISMA unidad
con el mismo hash, versión de catálogo y configuración. Guarda siempre el bruto.
"""

from __future__ import annotations

from typing import Any


def normalize(
    answers: dict[str, Any], bank: dict[str, Any], manifest: dict[str, Any], approved_ids: set[str]
) -> dict[str, Any]:
    """approved_ids lo determina TU política calibrada o revisión humana.

    No se deduce aprobación de un umbral fijo de confidence. Una respuesta excluida
    se conserva en raw, pero no se publica como etiqueta aceptada.
    """
    output: dict[str, Any] = {}
    for qid, question in bank.items():
        answer = answers.get(qid)
        if answer is None:
            output[qid] = {"status": "not_evaluated", "value": None}
            continue
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ValueError(f"Tipo de respuesta inesperado: {qid}")
        record: dict[str, Any] = {"status": "review_required", "value": None, "raw": answer}
        meta = manifest["preguntas"][qid]
        if question["type"] == "choice":
            value = answer.get("choice")
            if value not in question["criteria"]:
                raise ValueError(f"Opción fuera del vocabulario: {qid}={value!r}")
            if qid in approved_ids:
                record.update(status="accepted", value=value)
        elif question["type"] == "score":
            value = answer.get("score")
            top = len(question["criteria"]) - 1
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not 0 <= value <= top
            ):
                raise ValueError(f"Score fuera de escala: {qid}")
            gate_id = meta["control_aplicabilidad"]
            gate_answer = answers.get(gate_id, {})
            gate = gate_answer.get("choice")
            if gate_id not in approved_ids:
                record["status"] = "applicability_unresolved"
            elif gate == "no_aplica":
                record["status"] = "not_applicable"
            elif gate != "evaluable":
                record["status"] = "insufficient_evidence"
            elif qid in approved_ids:
                record.update(status="accepted", value=value, score_0_100=100 * value / top)
        output[qid] = record
    return output
