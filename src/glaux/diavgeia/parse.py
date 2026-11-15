"""Turn Diavgeia API JSON into row values. Pure: no network, no database.

Field meanings come from the probe (docs/build-spec.md, assumptions A1 to A18). In particular:
`issueDate` is midnight in either Athens time or UTC (A14), so the day is the Athens-local date of
the timestamp; and `submissionTimestamp` is the time of the last modification, not of the first
submission (A10), so it is stored as `modified_at`.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

ATHENS = ZoneInfo("Europe/Athens")

# Greek capitals, as the API returns them in decisionTypeId.
SPENDING_TYPES = ("Β.1.3", "Β.2.1", "Β.2.2", "Δ.1", "Δ.2.1", "Δ.2.2")

# Digits and Greek capitals; 5, 7, 8 or 10 characters seen before the hyphen (A16).
ADA_PATTERN = re.compile(r"^[0-9Α-Ω]{5,10}-[0-9Α-Ω]{3}$")
# Two year digits, a KIMDIS record type, nine digits (A15).
ADAM_PATTERN = re.compile(r"^\d{2}(?:REQ|PROC|AWRD|SYMV|PAY)\d{9}$")

# Fields that identify a person and that no derived table needs.
ORGANIZATION_PERSONAL_FIELDS = ("odeManagerEmail",)


class ParseError(ValueError):
    """A record lacks a field that every record is expected to have."""


def utc_from_ms(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC)


def athens_date(ms: int) -> dt.date:
    """The calendar day of a timestamp in Athens. Right for both issue date encodings (A14)."""
    return dt.datetime.fromtimestamp(ms / 1000, ATHENS).date()


def is_valid_ada(value: str) -> bool:
    return bool(ADA_PATTERN.match(value))


def is_valid_adam(value: str) -> bool:
    return bool(ADAM_PATTERN.match(value))


def to_decimal(value: int | float | str | Decimal) -> Decimal:
    """An API number as Decimal. Floats go through their shortest repr, which equals the JSON
    literal for any amount with up to 15 significant digits."""
    if isinstance(value, bool):
        raise TypeError("a boolean is not an amount")
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(value)


@dataclass(frozen=True)
class DecisionRow:
    ada: str
    version_id: str
    status: str
    subject: str
    issue_date: dt.date
    modified_at: dt.datetime
    published_at: dt.datetime | None
    org_uid: str
    type_uid: str
    private_data: bool
    document_url: str | None
    adam: str | None
    raw: dict[str, Any]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchPage:
    total: int
    page: int
    size: int
    actual_size: int
    query: str
    decisions: list[DecisionRow]


@dataclass(frozen=True)
class DecisionTypeRow:
    uid: str
    label: str
    parent_uid: str | None
    allowed_in_decisions: bool
    raw: dict[str, Any]


@dataclass(frozen=True)
class OrganizationRow:
    uid: str
    label: str
    category: str | None
    status: str | None
    vat_number: str | None
    supervisor_uid: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class VersionRow:
    version_id: str
    status: str
    at: dt.datetime
    description: str | None
    corrected_version_id: str | None


_REQUIRED_DECISION_FIELDS = (
    "ada",
    "versionId",
    "status",
    "subject",
    "issueDate",
    "submissionTimestamp",
    "organizationId",
    "decisionTypeId",
    "privateData",
)


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def parse_decision(record: dict[str, Any]) -> DecisionRow:
    missing = [f for f in _REQUIRED_DECISION_FIELDS if record.get(f) is None]
    if missing:
        raise ParseError(f"decision {record.get('ada')!r} lacks {', '.join(missing)}")

    warnings = []
    ada = record["ada"]
    if not is_valid_ada(ada):
        warnings.append("ada_format")

    extra = record.get("extraFieldValues") or {}
    adam = _blank_to_none(extra.get("adam")) or _blank_to_none(record.get("adam"))
    if adam is not None and not is_valid_adam(adam):
        warnings.append("adam_format")

    published = record.get("publishTimestamp")
    return DecisionRow(
        ada=ada,
        version_id=record["versionId"],
        status=record["status"],
        subject=record["subject"],
        issue_date=athens_date(record["issueDate"]),
        modified_at=utc_from_ms(record["submissionTimestamp"]),
        published_at=utc_from_ms(published) if published else None,
        org_uid=str(record["organizationId"]),
        type_uid=record["decisionTypeId"],
        private_data=bool(record["privateData"]),
        document_url=_blank_to_none(record.get("documentUrl")),
        adam=adam,
        raw=record,
        warnings=tuple(warnings),
    )


def parse_search_page(data: dict[str, Any]) -> SearchPage:
    info = data.get("info")
    if info is None or "decisions" not in data:
        raise ParseError("search response lacks info or decisions")
    return SearchPage(
        total=int(info["total"]),
        page=int(info["page"]),
        size=int(info["size"]),
        actual_size=int(info["actualSize"]),
        query=info.get("query", ""),
        decisions=[parse_decision(d) for d in data["decisions"]],
    )


def parse_decision_types(data: dict[str, Any]) -> list[DecisionTypeRow]:
    return [
        DecisionTypeRow(
            uid=t["uid"],
            label=t["label"],
            parent_uid=t.get("parent"),
            allowed_in_decisions=bool(t.get("allowedInDecisions")),
            raw=t,
        )
        for t in data["decisionTypes"]
    ]


def parse_organization(record: dict[str, Any]) -> OrganizationRow:
    raw = {k: v for k, v in record.items() if k not in ORGANIZATION_PERSONAL_FIELDS}
    return OrganizationRow(
        uid=str(record["uid"]),
        label=record["label"],
        category=record.get("category"),
        status=record.get("status"),
        vat_number=_blank_to_none(record.get("vatNumber")),
        supervisor_uid=_blank_to_none(record.get("supervisorId")),
        raw=raw,
    )


def parse_versionlog(data: dict[str, Any]) -> list[VersionRow]:
    """Versions, oldest first. The `creator` field identifies a user and is not kept."""
    rows = [
        VersionRow(
            version_id=v["versionId"],
            status=v["status"],
            at=utc_from_ms(v["versionTimestamp"]),
            description=_blank_to_none(v.get("description")),
            corrected_version_id=v.get("correctedVersionId"),
        )
        for v in data["versions"]
    ]
    return sorted(rows, key=lambda r: r.at)
