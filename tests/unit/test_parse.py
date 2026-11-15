import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest

from glaux.diavgeia.parse import (
    ATHENS,
    SPENDING_TYPES,
    ParseError,
    athens_date,
    is_valid_ada,
    is_valid_adam,
    parse_decision,
    parse_decision_types,
    parse_organization,
    parse_search_page,
    parse_versionlog,
    to_decimal,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "diavgeia"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def ms(year, month, day, hour=0, minute=0, tz=dt.UTC) -> int:
    return int(dt.datetime(year, month, day, hour, minute, tzinfo=tz).timestamp() * 1000)


# Issue dates (A14)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (ms(2026, 10, 14, tz=ATHENS), dt.date(2026, 10, 14)),  # Athens midnight, summer
        (ms(2026, 10, 14), dt.date(2026, 10, 14)),  # UTC midnight = 03:00 Athens
        (ms(2026, 11, 12, tz=ATHENS), dt.date(2026, 11, 12)),  # Athens midnight, winter
        (ms(2026, 11, 12), dt.date(2026, 11, 12)),  # UTC midnight = 02:00 Athens
        (ms(2026, 10, 25, tz=ATHENS), dt.date(2026, 10, 25)),  # day summer time ends
        (ms(2026, 10, 25), dt.date(2026, 10, 25)),
        (ms(2026, 3, 29, tz=ATHENS), dt.date(2026, 3, 29)),  # day summer time starts
        (ms(2026, 3, 29), dt.date(2026, 3, 29)),
    ],
)
def test_athens_date_handles_both_encodings(timestamp, expected):
    assert athens_date(timestamp) == expected


def test_advanced_fixture_has_both_encodings_and_one_day():
    page = parse_search_page(fixture("search_advanced_page.json"))
    hours = {
        dt.datetime.fromtimestamp(d.raw["issueDate"] / 1000, ATHENS).hour for d in page.decisions
    }
    assert hours == {0, 3}
    assert {d.issue_date for d in page.decisions} == {dt.date(2026, 10, 14)}


# Search pages


def test_search_page_fixture():
    page = parse_search_page(fixture("search_page.json"))
    assert page.total == 1341
    assert page.size == 500
    assert "Αναρτημένη" in page.query  # the hidden default filter (A2)
    assert {d.type_uid for d in page.decisions} == set(SPENDING_TYPES)
    assert {d.issue_date for d in page.decisions} == {dt.date(2026, 10, 14)}
    assert all(d.status == "PUBLISHED" and not d.private_data for d in page.decisions)
    assert all(d.warnings == () for d in page.decisions)


def test_decision_fields():
    page = parse_search_page(fixture("search_page.json"))
    by_type = {d.type_uid: d for d in page.decisions}
    b21 = by_type["Β.2.1"]
    assert b21.ada == "93ΨΣ7ΛΛ-8ΒΘ"
    assert b21.org_uid == "5009"
    assert b21.adam is None
    assert b21.document_url == "https://diavgeia.gov.gr/doc/93ΨΣ7ΛΛ-8ΒΘ"
    assert b21.modified_at.tzinfo is dt.UTC
    assert by_type["Β.2.2"].adam == "26PAY020192752"
    assert by_type["Δ.2.1"].adam == "26PROC020057770"


def test_detail_endpoint_matches_search_record():
    detail = parse_decision(fixture("decision_B21.json"))
    from_search = next(
        d for d in parse_search_page(fixture("search_page.json")).decisions if d.ada == detail.ada
    )
    assert detail == from_search


def test_revoked_decision():
    page = parse_search_page(fixture("search_advanced_revoked.json"))
    revoked = page.decisions[0]
    assert revoked.status == "REVOKED"
    assert revoked.issue_date == dt.date(2026, 10, 20)
    # submissionTimestamp moved to the revocation; publishTimestamp kept the first publication (A10)
    assert revoked.modified_at == dt.datetime(2026, 11, 12, 12, 52, 23, 0, dt.UTC).replace(
        microsecond=revoked.modified_at.microsecond
    )
    assert revoked.published_at.date() == dt.date(2026, 10, 20)


def test_missing_required_field_is_an_error():
    record = fixture("decision_B21.json")
    del record["issueDate"]
    with pytest.raises(ParseError, match="issueDate"):
        parse_decision(record)


def test_odd_identifiers_are_warnings_not_errors():
    record = fixture("decision_B21.json")
    record["ada"] = "93ΨΣ7ΛΛ-8BΘ"  # Latin B
    record["extraFieldValues"]["adam"] = "26PAY0201"
    row = parse_decision(record)
    assert row.warnings == ("ada_format", "adam_format")


def test_search_page_without_info_is_an_error():
    with pytest.raises(ParseError):
        parse_search_page({"decisions": []})


# Identifiers (A15, A16)


@pytest.mark.parametrize(
    "ada", ["93ΨΣ7ΛΛ-8ΒΘ", "Ρ9ΘΗ469Η1Γ-Ο24", "ΡΤΕΨΩΨΟ-ΩΙΓ", "Ρ2ΒΠ6-4ΣΗ", "98ΗΝΩΡ5-2ΜΒ"]
)
def test_valid_adas(ada):
    assert is_valid_ada(ada)


@pytest.mark.parametrize(
    "ada", ["93ΨΣ7ΛΛ-8BΘ", "ΡΤΕΨ-ΩΙΓ", "Ρ9ΘΗ469Η1Γ1-Ο24", "Ρ9ΘΗ469Η1Γ-Ο2", "ρ9θη469η1γ-ο24", ""]
)
def test_invalid_adas(ada):
    assert not is_valid_ada(ada)


@pytest.mark.parametrize("adam", ["26PAY020192752", "26REQ020194481", "26AWRD020180914"])
def test_valid_adams(adam):
    assert is_valid_adam(adam)


@pytest.mark.parametrize(
    "adam", ["26PAY02019275", "26pay020192752", "PAY020192752", "26XYZ020192752"]
)
def test_invalid_adams(adam):
    assert not is_valid_adam(adam)


# Amounts


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (297.64, "297.64"),
        (3534.0, "3534.0"),
        (346561.4, "346561.4"),
        (2026, "2026"),
        ("0.10", "0.10"),
    ],
)
def test_to_decimal_keeps_the_json_literal(value, expected):
    assert to_decimal(value) == Decimal(expected)
    assert str(to_decimal(value)) == expected


def test_to_decimal_rejects_booleans():
    with pytest.raises(TypeError):
        to_decimal(True)


# Reference data and version logs


def test_decision_types():
    types = parse_decision_types(fixture("types.json"))
    uids = {t.uid for t in types}
    assert len(types) == 43
    assert set(SPENDING_TYPES) <= uids
    assert all(t.parent_uid is None or t.parent_uid in uids for t in types)


def test_organizations_drop_personal_fields():
    orgs = [parse_organization(o) for o in fixture("organizations.json")["organizations"]]
    assert len(orgs) == 8
    assert all("odeManagerEmail" not in o.raw for o in orgs)
    region = next(o for o in orgs if o.uid == "5009")
    assert region.vat_number == "997612598"
    assert region.category == "REGION"


def test_versionlog_of_a_revoked_decision():
    versions = parse_versionlog(fixture("versionlog_revoked.json"))
    assert [v.status for v in versions] == ["PUBLISHED", "REVOKED"]
    assert "διπλής ανάρτησης" in versions[-1].description
    assert not hasattr(versions[0], "creator")


def test_search_terms_the_harvest_relies_on_still_exist():
    terms = {t["term"] for t in fixture("search_terms.json")["terms"]}
    assert {"issueDate", "submissionTimestamp", "status", "amount", "decisionTypeUid"} <= terms
