from __future__ import annotations

import json
import unittest
from importlib.resources import files

from jevdocs.catalog.crear_peticiones import build_requests, load_json, select_ids, validate_state
from jevdocs.catalog.normalizar_respuestas import normalize

ROOT = files("jevdocs.catalog")
BANK = load_json(ROOT / "preguntas_jev.json")
MANIFEST = load_json(ROOT / "catalogo.json")
STATE = {
    "document": {
        "id": "test",
        "extraction": {
            "coverage": "full",
            "structure_preserved": True,
            "visual_content_described": False,
        },
        "segments": [{"id": "s1", "text": "Documento de prueba suficientemente legible."}],
    }
}


class CatalogueTests(unittest.TestCase):
    def test_counts_and_unique_membership(self):
        self.assertEqual(len(BANK), 235)
        self.assertEqual(len(MANIFEST["nucleo"]), 49)
        members = [q for group in MANIFEST["grupos"].values() for q in group["preguntas"]]
        self.assertEqual(len(members), len(set(members)))
        self.assertEqual(set(members), set(BANK))
        self.assertEqual(set(MANIFEST["preguntas"]), set(BANK))

    def test_native_contract(self):
        for q in BANK.values():
            self.assertEqual(set(q), {"type", "instructions", "criteria"})
            self.assertIsInstance(q["instructions"]["pregunta"], str)
            if q["type"] == "choice":
                self.assertIsInstance(q["criteria"], dict)
                self.assertTrue(2 <= len(q["criteria"]) <= 255)
            elif q["type"] == "score":
                self.assertIsInstance(q["criteria"], list)
                self.assertTrue(2 <= len(q["criteria"]) <= 10)
            else:
                self.fail(q["type"])

    def test_score_gates(self):
        for qid, q in BANK.items():
            if q["type"] == "score":
                gate = MANIFEST["preguntas"][qid]["control_aplicabilidad"]
                self.assertEqual(
                    set(BANK[gate]["criteria"]), {"evaluable", "no_aplica", "no_determinable"}
                )

    def test_bank_has_no_placeholders(self):
        text = json.dumps(BANK, ensure_ascii=False)
        self.assertNotIn("SUSTITUIR_", text)
        self.assertNotIn("TODO:", text)

    def test_all_json_parse(self):
        for path in ROOT.iterdir():
            if not path.name.endswith(".json"):
                continue
            self.assertIsNotNone(load_json(path))

    def test_selection(self):
        self.assertEqual(len(select_ids(MANIFEST, core=True)), 49)
        self.assertEqual(len(select_ids(MANIFEST, ["temas"])), 38)
        self.assertEqual(len(select_ids(MANIFEST, ["todos"])), 235)
        with self.assertRaises(ValueError):
            select_ids(MANIFEST, ["inventado"])

    def test_batches_and_pairs(self):
        ids = select_ids(MANIFEST, ["todos"])
        batches = build_requests(STATE, BANK, MANIFEST, ids, "jev-latest", 32)
        all_ids = [q for p in batches for q in p["questions"]]
        self.assertEqual(set(all_ids), set(ids))
        self.assertEqual(len(all_ids), len(ids))
        for p in batches:
            self.assertLessEqual(len(p["questions"]), 32)
            self.assertEqual(set(p), {"state", "model", "questions"})
            for qid, q in p["questions"].items():
                if q["type"] == "score":
                    self.assertIn(
                        MANIFEST["preguntas"][qid]["control_aplicabilidad"], p["questions"]
                    )

    def test_empty_and_placeholder_rejected(self):
        with self.assertRaises(ValueError):
            validate_state(load_json(ROOT / "estado_plantilla.json"))
        with self.assertRaises(ValueError):
            validate_state(
                {"document": {"extraction": STATE["document"]["extraction"], "segments": []}}
            )

    def test_no_absent_default(self):
        values = normalize({}, BANK, MANIFEST, set())
        self.assertEqual(values["tiene_tablas"], {"status": "not_evaluated", "value": None})

    def test_no_score_if_not_applicable(self):
        gate = "evaluabilidad_accionabilidad"
        qid = "score_accionabilidad"
        raw = {
            gate: {"type": "choice", "choice": "no_aplica"},
            qid: {"type": "score", "score": 0.0},
        }
        value = normalize(raw, BANK, MANIFEST, {gate, qid})[qid]
        self.assertEqual(value["status"], "not_applicable")
        self.assertIsNone(value["value"])

    def test_score_normalization(self):
        gate = "evaluabilidad_accionabilidad"
        qid = "score_accionabilidad"
        raw = {
            gate: {"type": "choice", "choice": "evaluable"},
            qid: {"type": "score", "score": 3.2},
        }
        values = normalize(raw, BANK, MANIFEST, {gate, qid})
        self.assertEqual(values[qid]["value"], 3.2)
        self.assertEqual(values[qid]["score_0_100"], 80.0)

    def test_unaccepted_gate_blocks_score(self):
        gate = "evaluabilidad_accionabilidad"
        qid = "score_accionabilidad"
        raw = {
            gate: {"type": "choice", "choice": "evaluable"},
            qid: {"type": "score", "score": 3.2},
        }
        self.assertEqual(
            normalize(raw, BANK, MANIFEST, {qid})[qid]["status"], "applicability_unresolved"
        )

    def test_synthetic_expectations_valid(self):
        for case in load_json(ROOT / "casos_prueba_sinteticos.json")["casos"]:
            validate_state(case["state"])
            for qid, options in case["opciones_aceptables"].items():
                self.assertIn(qid, BANK)
                self.assertTrue(set(options) <= set(BANK[qid]["criteria"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
