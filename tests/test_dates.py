from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fbwatch.dates import from_epoch, parse_facebook_date, parse_user_date

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=ZoneInfo("Europe/Athens"))


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Τετάρτη 4 Οκτωβρίου 2026 στις 10:15 π.μ.", "2026-10-04T10:15:00+03:00"),
        ("Τετάρτη 4 Οκτωβρίου 2026 στις 10:15 μ.μ.", "2026-10-04T22:15:00+03:00"),
        ("October 4, 2026 at 3:15 PM", "2026-10-04T15:15:00+03:00"),
        ("Wednesday, October 4, 2026 at 12:05 AM", "2026-10-04T00:05:00+03:00"),
        ("4 Oct 2026", "2026-10-04T00:00:00+03:00"),
        ("4 Οκτ", "2026-10-04T00:00:00+03:00"),
        ("28 Σεπ στις 21:05", "2026-09-28T21:05:00+03:00"),
        ("Sep 28", "2026-09-28T00:00:00+03:00"),
        ("Δευ 12 Νοε", "2025-11-12T00:00:00+02:00"),  # μέλλον -> περσινό έτος
        ("Χθες στις 10:15", "2026-10-03T10:15:00+03:00"),
        ("Yesterday at 10:15 AM", "2026-10-03T10:15:00+03:00"),
        ("5 ώρες", "2026-10-04T07:00:00+03:00"),
        ("5 h", "2026-10-04T07:00:00+03:00"),
        ("3 d", "2026-10-01T12:00:00+03:00"),
        ("Μόλις τώρα", "2026-10-04T12:00:00+03:00"),
        ("04/10/2026", "2026-10-04T00:00:00+03:00"),
        ("2026-10-04T10:15:00", "2026-10-04T10:15:00+03:00"),
        ("1759564800", "2025-10-04T11:00:00+03:00"),
    ],
)
def test_parse_facebook_date(text, expected):
    dt = parse_facebook_date(text, now=NOW)
    assert dt is not None, text
    assert dt.isoformat(timespec="seconds") == expected


def test_parse_unknown_returns_none():
    assert parse_facebook_date("σκουπίδια", now=NOW) is None
    assert parse_facebook_date("", now=NOW) is None
    assert parse_facebook_date(None, now=NOW) is None


def test_from_epoch_handles_ms_and_garbage():
    assert from_epoch("1759564800000").isoformat(timespec="seconds") == "2025-10-04T11:00:00+03:00"
    assert from_epoch("abc") is None
    assert from_epoch("12") is None


def test_parse_user_date():
    assert parse_user_date("2026-10-04").isoformat() == "2026-10-04T00:00:00+03:00"
    assert parse_user_date("04/10/2026", end_of_day=True).isoformat() == "2026-10-04T23:59:59+03:00"
    assert parse_user_date("2026-10-04 08:30").hour == 8
    with pytest.raises(ValueError):
        parse_user_date("4 Οκτ 2026")
