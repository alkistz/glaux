import datetime as dt
import json

import httpx

from glaux.http import PoliteClient
from glaux.probe import (
    BASE_URL,
    FILTER_PROBE_BUDGET,
    MAX_REQUESTS,
    day_range,
    run_filter_probe,
    run_probe,
    shape,
)

DECISION = {
    "ada": "ΑΒΓΔ123456-ΕΖΗ",
    "decisionTypeId": "Β.2.1",
    "privateData": False,
    "documentUrl": "https://diavgeia.gov.gr/doc/ΑΒΓΔ123456-ΕΖΗ",
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.startswith("/doc/"):
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})
    if path.endswith("organizations.json"):
        return httpx.Response(404, json={"error": "nope"})
    body = {"info": {"total": 1}, "decisions": [DECISION]} if "search" in path else {"ok": 1}
    return httpx.Response(200, json=body)


def test_shape_summarises_structure():
    data = {"info": {"total": 3}, "decisions": [{"ada": "x", "n": 1}], "deep": {"a": {"b": 1}}}
    assert shape(data) == {
        "info": {"total": "int"},
        "decisions": ["list[1]", {"ada": "str", "n": "int"}],
        "deep": {"a": "dict[1]"},
    }


def test_probe_saves_everything_and_stays_in_budget(tmp_path):
    client = PoliteClient(
        BASE_URL, "glaux/test", 0.0, transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    index = run_probe(client, tmp_path, dt.date(2026, 10, 14))

    assert client.stats.requests <= MAX_REQUESTS
    saved = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert saved == index
    names = [e["name"] for e in index]
    assert "decision_Β.2.1" in names
    assert "document" in names
    failed = [e for e in index if e.get("error")]
    assert [e["name"] for e in failed] == ["organizations"]
    pdf = next(e for e in index if e["name"] == "document")
    assert (tmp_path / pdf["file"]).read_bytes() == b"%PDF-1.4"


def test_day_range_covers_the_whole_day():
    assert day_range("issueDate", dt.date(2026, 10, 14)) == (
        "issueDate:[DT(2026-10-14T00:00:00) TO DT(2026-10-14T23:59:59)]"
    )


def test_filter_probe_follows_a_revoked_decision_to_its_versionlog(tmp_path):
    seen = []

    def filter_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "advanced" in request.url.path:
            return httpx.Response(200, json={"info": {"total": 1}, "decisions": [DECISION]})
        return httpx.Response(200, json={"terms": []})

    client = PoliteClient(
        BASE_URL,
        "glaux/test",
        0.0,
        transport=httpx.MockTransport(filter_handler),
        sleep=lambda s: None,
    )
    index = run_filter_probe(client, tmp_path, dt.date(2026, 10, 14), dt.date(2026, 11, 13))

    assert client.stats.requests <= FILTER_PROBE_BUDGET
    assert index[-1]["name"] == "versionlog_revoked"
    assert seen[-1].url.path.endswith(f"decisions/{DECISION['ada']}/versionlog.json")
    queries = [r.url.params.get("q") for r in seen if r.url.params.get("q")]
    assert any(q.startswith("amount:[25000 TO 30000]") for q in queries)
