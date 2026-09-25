from datetime import date, datetime

from chore_stars.seed import week_advertised_capacity
from chore_stars.timeutil import infraction_cutoff, quiet_cutoff, week_start


def test_week_advertised_capacity_is_template_sum():
    from chore_stars.seed import TEMPLATES

    slugs = {row[0] for row in TEMPLATES}
    assert "take-out-trash" in slugs
    assert "burn-boxes" in slugs
    assert {"edge", "blow", "outdoor-weeding"} <= slugs
    assert "edge-prune-blow" not in slugs
    assert week_advertised_capacity() == 128


def test_thursday_is_start():
    thu = datetime(2026, 9, 24, 10, 0)  # Thursday
    assert week_start(thu) == date(2026, 9, 24)


def test_wednesday_belongs_to_previous_thursday():
    wed = datetime(2026, 9, 23, 22, 0)
    assert week_start(wed) == date(2026, 9, 17)


def test_cutoffs():
    thu = date(2026, 9, 24)
    assert quiet_cutoff(thu, "America/Indiana/Indianapolis").hour == 18
    assert infraction_cutoff(thu, "America/Indiana/Indianapolis").date() == date(2026, 9, 26)
