"""glaux probe: a small, fixed set of requests that checks our assumptions about the Diavgeia API.

Every response is saved unchanged so fixtures can be cut from it. See stage 1 in
docs/build-spec.md for what each request is meant to check.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from glaux.http import PoliteClient, RequestFailed

BASE_URL = "https://diavgeia.gov.gr/opendata/"
# Greek capitals, as the API returns them in decisionTypeId.
SPENDING_TYPES = ("Β.1.3", "Β.2.1", "Β.2.2", "Δ.1", "Δ.2.1", "Δ.2.2")
MAX_REQUESTS = 19  # plus the single exploratory request made by hand, 20 in all


class BudgetSpent(Exception):
    pass


def shape(value: Any, depth: int = 0, max_depth: int = 2) -> Any:
    """A compact structural summary of parsed JSON: dict keys with their value types."""
    if isinstance(value, dict):
        if depth >= max_depth:
            return f"dict[{len(value)}]"
        return {k: shape(v, depth + 1, max_depth) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return "list[0]"
        return [f"list[{len(value)}]", shape(value[0], depth, max_depth)]
    return type(value).__name__


class Probe:
    def __init__(self, client: PoliteClient, out_dir: Path, budget: int = MAX_REQUESTS):
        self.client = client
        self.out_dir = out_dir
        self.budget = budget
        self.index: list[dict[str, Any]] = []

    def fetch(self, name: str, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET and save the body. Returns parsed JSON, raw bytes, or None on failure."""
        if self.client.stats.requests >= self.budget:
            raise BudgetSpent(name)
        started = time.monotonic()
        error = None
        try:
            response = self.client.get(url, params=params)
        except RequestFailed as exc:
            response, error = exc.response, str(exc)
        entry: dict[str, Any] = {
            "name": name,
            "url": str(response.request.url) if response is not None else url,
            "status": response.status_code if response is not None else None,
            "content_type": response.headers.get("content-type") if response is not None else None,
            "bytes": len(response.content) if response is not None else 0,
            "seconds": round(time.monotonic() - started, 2),
            "error": error,
        }
        self.index.append(entry)
        if response is None:
            return None
        content_type = entry["content_type"] or ""
        is_json = "json" in content_type
        suffix = ".json" if is_json else ".pdf" if "pdf" in content_type else ".bin"
        path = self.out_dir / f"{len(self.index):02d}_{name}{suffix}"
        path.write_bytes(response.content)
        entry["file"] = path.name
        if error is not None:
            return None
        if is_json:
            data = response.json()
            entry["shape"] = shape(data)
            if isinstance(data, dict) and "info" in data:
                entry["info"] = data["info"]
            return data
        return response.content


def _pick_decisions(decisions: list[dict], wanted: tuple[str, ...], n: int) -> list[dict]:
    """One public decision per wanted type, in order, until n are picked."""
    picked: list[dict] = []
    for type_id in wanted:
        for d in decisions:
            if d.get("decisionTypeId") == type_id and not d.get("privateData"):
                picked.append(d)
                break
        if len(picked) == n:
            break
    return picked


def run_probe(client: PoliteClient, out_dir: Path, day: dt.date) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = Probe(client, out_dir)
    d = day.isoformat()
    one_day = {"from_issue_date": d, "to_issue_date": d}
    try:
        p.fetch("types", "types.json")
        for type_id in SPENDING_TYPES:
            p.fetch(f"type_details_{type_id}", f"types/{type_id}/details.json")
        p.fetch("organizations", "organizations.json")

        page = p.fetch("search_day_size500", "search.json", {**one_day, "size": 500})
        p.fetch("search_day_size1000", "search.json", {**one_day, "size": 1000})
        p.fetch("search_day_type_B21", "search.json", {**one_day, "type": "Β.2.1", "size": 10})
        p.fetch("search_day_status_all", "search.json", {**one_day, "status": "all", "size": 10})
        month_start = day.replace(day=1).isoformat()
        p.fetch(
            "search_month_deep_page",
            "search.json",
            {"from_issue_date": month_start, "to_issue_date": d, "size": 500, "page": 40},
        )

        decisions = (page or {}).get("decisions", []) if isinstance(page, dict) else []
        chosen = _pick_decisions(decisions, ("Β.2.1", "Δ.1", "Β.2.2", "Β.1.3", "Δ.2.2"), 3)
        for dec in chosen:
            p.fetch(f"decision_{dec['decisionTypeId']}", f"decisions/{dec['ada']}.json")
        if chosen:
            p.fetch("versionlog", f"decisions/{chosen[0]['ada']}/versionlog.json")
            p.fetch("document", chosen[0]["documentUrl"])
    except BudgetSpent as exc:
        p.index.append({"name": str(exc), "error": "request budget spent, skipped"})
    finally:
        (out_dir / "index.json").write_text(
            json.dumps(p.index, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return p.index
