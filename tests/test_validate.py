"""R1: missing or invalid ticket information is rejected with a field-level message.
AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil."""
from core.validate import validate_ticket


def _req(t):
    return {r["req_id"]: r for r in t["requesters"]}


def test_r1_all_valid_scenario_tickets_pass(toronto):
    t, _ = toronto
    for row in t["tickets"]:
        assert validate_ticket(row, _req(t)) == [], row


def test_r1_each_invalid_scenario_ticket_is_rejected_on_the_expected_field(toronto):
    t, bundle = toronto
    expected = [{"severity"}, {"people_affected"}, {"servings_requested"}, {"deadline"},
                {"req_id"}, {"refrigerated"}, {"severity", "deadline"}]
    assert len(bundle.extra_tickets) == len(expected)
    for row, fields in zip(bundle.extra_tickets, expected):
        got = {f for f, _ in validate_ticket(row, _req(t))}
        assert fields <= got, (row["_expect"], got)


def test_r1_aadil_ticket_rejected_only_for_missing_severity(aadil):
    t, _ = aadil
    errors = validate_ticket(t["tickets"][0], _req(t))
    assert [f for f, _ in errors] == ["severity"]


def test_r1_boolean_is_not_accepted_as_a_number(toronto):
    t, _ = toronto
    row = dict(t["tickets"][0], servings_requested=True)
    assert ("servings_requested" in {f for f, _ in validate_ticket(row, _req(t))})
