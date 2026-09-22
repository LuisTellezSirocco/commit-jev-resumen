import json
import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest

from jevdocs.core import (
    INDIVIDUAL_BYTES,
    REQUEST_BYTES,
    JevClient,
    aggregate,
    batch_questions,
    damaged_text,
    load_catalog,
    make_units,
    packed,
    validate_response,
)
from jevdocs.server import make_handler


def answer(value, confidence=0.95):
    return {
        "type": "choice",
        "choice": value,
        "confidence": confidence,
        "probabilities": {value: 1},
    }


def document(answers, coverage="full"):
    return {
        "units": [{"id": f"u{i}", "pages": [i + 1], "answers": a} for i, a in enumerate(answers)],
        "extraction": {"coverage": coverage},
    }


@pytest.fixture
def catalog():
    return load_catalog()


def test_partial_negative_never_global_absence(catalog):
    bank, manifest = catalog
    doc = document([{"tiene_codigo": answer("no_observado")}], "partial")
    f = aggregate(doc, bank, manifest)["tiene_codigo"]
    assert f["value"] is None and f["status"] == "insufficient_evidence"


def test_positive_in_one_unit_survives_missing_other_unit(catalog):
    bank, manifest = catalog
    doc = document([{}, {"tiene_codigo": answer("presente")}])
    f = aggregate(doc, bank, manifest)["tiene_codigo"]
    assert f["value"] == "presente" and f["scope"] == "segments"
    assert f["observations"][0]["pages"] == [2]


def test_unasked_never_becomes_absent(catalog):
    bank, manifest = catalog
    f = aggregate(document([{}]), bank, manifest)["tiene_codigo"]
    assert f["status"] == "not_evaluated" and f["value"] is None


def test_low_confidence_not_searchable(catalog):
    bank, manifest = catalog
    f = aggregate(document([{"tiene_codigo": answer("presente", 0.4)}]), bank, manifest)[
        "tiene_codigo"
    ]
    assert f["value"] is None and f["status"] == "review_required"


def test_local_type_is_not_global_consensus(catalog):
    bank, manifest = catalog
    f = aggregate(document([{"tipo_documental": answer("contrato_convenio")}, {}]), bank, manifest)[
        "tipo_documental"
    ]
    assert f["value"] is None and f["status"] == "segment_values"
    assert f["values"] == ["contrato_convenio"]


def test_conflicting_types_retained(catalog):
    bank, manifest = catalog
    f = aggregate(
        document([{"tipo_documental": answer("factura")}, {"tipo_documental": answer("informe")}]),
        bank,
        manifest,
    )["tipo_documental"]
    assert f["status"] == "conflicting" and f["value"] is None


@pytest.mark.parametrize(
    "gate,confidence,expected",
    [
        ("no_aplica", 0.9, "not_applicable"),
        ("evaluable", 0.2, "applicability_unresolved"),
        ("no_determinable", 0.9, "insufficient_evidence"),
    ],
)
def test_score_gate(catalog, gate, confidence, expected):
    bank, manifest = catalog
    k = next(k for k, q in bank.items() if q["type"] == "score")
    g = manifest["preguntas"][k]["control_aplicabilidad"]
    a = {
        k: {
            "type": "score",
            "score": 3.7,
            "confidence": 0.99,
            "probabilities": {"3": 0.3, "4": 0.7},
        },
        g: answer(gate, confidence),
    }
    f = aggregate(document([a]), bank, manifest)[k]
    assert f["value"] is None
    assert f["observations"][0]["status"] == expected


def test_scores_never_averaged(catalog):
    bank, manifest = catalog
    k = next(k for k, q in bank.items() if q["type"] == "score")
    g = manifest["preguntas"][k]["control_aplicabilidad"]
    observations = [
        {
            g: answer("evaluable"),
            k: {"type": "score", "score": v, "confidence": 1, "probabilities": {str(v): 1}},
        }
        for v in [0, 4]
    ]
    f = aggregate(document(observations), bank, manifest)[k]
    assert f["value"] is None and f["values"] == [0, 4]


def test_unicode_splits_preserve_every_character_and_budget(catalog):
    text = "Texto español 漢字🙂 con cifras 1.200,00 €\n" * 2000
    doc = {"pages": [{"page": 1, "text": text}], "extraction": {"coverage": "full"}}
    units = make_units(doc)
    assert "".join(s["text"] for u in units for s in u["state"]["document"]["segments"]) == text
    for unit in units:
        batches = list(batch_questions(unit["state"], catalog[0], "jev-1.13.0"))
        assert {k for batch in batches for k in batch} == set(catalog[0])
        for batch in batches:
            assert (
                len(
                    packed(
                        {"model": "jev-1.13.0", "state": unit["state"], "questions": batch}
                    ).encode()
                )
                <= REQUEST_BYTES
            )
            for q in batch.values():
                assert (
                    len(packed({"state": unit["state"], "question": q}).encode())
                    <= INDIVIDUAL_BYTES
                )


def test_broken_pdf_character_map_detected():
    assert damaged_text("0123¢\x7f\x81  x  x  # u u" * 100)
    assert not damaged_text(
        "CONDICIONES PARTICULARES. El asegurado podrá solicitar asistencia durante el viaje. " * 20
    )


def test_api_validation_rejects_nan_missing_and_invalid_options():
    q = {"q": {"type": "choice", "criteria": {"a": "A", "b": "B"}}}
    for a in [
        answer("wrong"),
        answer("a", float("nan")),
        {"type": "choice", "choice": "a", "confidence": 0.9, "probabilities": {"a": 0.2}},
    ]:
        with pytest.raises(ValueError):
            validate_response({"model": "jev", "answers": {"q": a}}, q)
    with pytest.raises(ValueError):
        validate_response({"model": "jev", "answers": {}}, q)


def test_cache_key_changes_with_question_and_contains_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "unit-test-secret")
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200, json={"model": "jev", "answers": {"q": answer("a")}, "usage": {"input_tokens": 3}}
        )

    client = JevClient(cache_dir=tmp_path, transport=httpx.MockTransport(handle))
    q = {"q": {"type": "choice", "instructions": "question", "criteria": {"a": "A", "b": "B"}}}
    assert not client.decide("state", q)["cached"]
    assert client.decide("state", q)["cached"]
    q["q"]["instructions"] = "changed"
    assert not client.decide("state", q)["cached"]
    assert len(calls) == 2
    assert all("unit-test-secret" not in p.read_text() for p in tmp_path.glob("*.json"))
    client.close()


def test_retry_transient_error(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test")
    monkeypatch.setattr("jevdocs.core.time.sleep", lambda _: None)
    calls = []

    def handle(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"retry-after": "1"})
            if len(calls) == 1
            else httpx.Response(200, json={"model": "jev", "answers": {"q": answer("a")}})
        )

    client = JevClient(cache_dir=tmp_path, transport=httpx.MockTransport(handle))
    client.decide("state", {"q": {"type": "choice", "criteria": {"a": "A"}}})
    assert len(calls) == 2
    client.close()


def test_server_private_files_and_foreign_origin_denied(tmp_path):
    (tmp_path / "index.json").write_text(json.dumps({"documents": []}))
    (tmp_path / "index.html").write_text("<h1>Test</h1>")
    (tmp_path / ".env").write_text("secret")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert httpx.get(url).status_code == 200
        assert httpx.get(url + "/.env").status_code == 404
        assert httpx.get(url + "/originals/%2e%2e/.env").status_code == 404
        assert httpx.get(url, headers={"Host": "attacker.invalid"}).status_code == 403
        assert (
            httpx.post(
                url + "/api/search",
                json={"query": "test"},
                headers={"Origin": "https://other.test"},
            ).status_code
            == 403
        )
        assert httpx.post(url + "/api/search", json={"query": ""}).status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_embedded_document_cannot_close_script_tag(tmp_path):
    from jevdocs.__main__ import build

    index = {
        "documents": [],
        "created_at": "2026-09-22",
        "models": ["test"],
        "source_dir": str(tmp_path),
        "run": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "untrusted_text": '</script><script>alert("document injection")</script>',
    }
    build(index, tmp_path / "output")
    html = (tmp_path / "output/index.html").read_text()
    assert index["untrusted_text"] not in html
    assert html.count("</script>") == 2
    assert "\\u003c/script\\u003e" in html
