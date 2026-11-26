"""Past Promos import placeholder: new P### ids follow the highest on file."""
from webapp_core.promo_id import next_past_promo_ids


def test_ids_continue_after_highest_past_id():
    assert next_past_promo_ids(["P001", "P003", "P002"], 2) == ["P004", "P005"]


def test_other_ids_ignored_and_empty_start_at_one():
    assert next_past_promo_ids(["NEW-007", None, "X9"], 1) == ["P001"]
    assert next_past_promo_ids([], 0) == []
