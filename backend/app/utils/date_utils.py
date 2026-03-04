from datetime import date, timedelta


def yesterday() -> date:
    """Return yesterday's date."""
    return date.today() - timedelta(days=1)


def days_ago(n: int) -> date:
    """Return the date n days ago."""
    return date.today() - timedelta(days=n)


def date_range(date_from: date, date_to: date):
    """Yield each date in [date_from, date_to] inclusive."""
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)
