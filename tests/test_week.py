from datetime import date, datetime

from chore_stars.seed import week_advertised_capacity
from chore_stars.timeutil import infraction_cutoff, quiet_cutoff, week_start


def test_full_week_advertised_is_100():
    assert week_advertised_capacity() == 100


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
