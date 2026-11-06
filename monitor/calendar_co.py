"""Colombian public holidays and the business-day review window."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

FIXED_HOLIDAYS = ((1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25))
MOVED_TO_MONDAY = ((1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11))
EASTER_OFFSETS_MOVED_TO_MONDAY = (43, 64, 71)


def easter_sunday(year: int) -> date:
    """Return Easter Sunday using the anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def next_monday(day: date) -> date:
    """Return the same day if it is a Monday, otherwise the following Monday."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def holidays(year: int) -> set[date]:
    """Return the national holidays of Colombia for a year."""
    easter = easter_sunday(year)
    result = {date(year, month, day) for month, day in FIXED_HOLIDAYS}
    result |= {next_monday(date(year, month, day)) for month, day in MOVED_TO_MONDAY}
    result |= {easter - timedelta(days=3), easter - timedelta(days=2)}
    result |= {next_monday(easter + timedelta(days=n)) for n in EASTER_OFFSETS_MOVED_TO_MONDAY}
    return result


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year)


def previous_business_day(day: date) -> date:
    day -= timedelta(days=1)
    while not is_business_day(day):
        day -= timedelta(days=1)
    return day


@dataclass(frozen=True)
class ReviewWindow:
    start: date
    end: date


def review_window(reference: date, business_days: int = 3) -> ReviewWindow:
    """Return the window covering the last N business days up to the reference.

    Weekends and holidays are skipped, so a Monday review after a long weekend
    still reaches back over the days the court could have been active.
    """
    if business_days < 1:
        raise ValueError("business_days must be at least 1")
    end = reference if is_business_day(reference) else previous_business_day(reference)
    start = end
    for _ in range(business_days - 1):
        start = previous_business_day(start)
    return ReviewWindow(start, end)
