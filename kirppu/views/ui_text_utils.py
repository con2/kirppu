import datetime
import typing

from django.template import defaultfilters


Lazy = typing.Callable[[str | None], str] | str


def _datetime(value: datetime.datetime | None) -> Lazy:
    def wrapped(fmt: str = "SHORT_DATETIME_FORMAT") -> str:
        if value is None:
            return ""
        return defaultfilters.date(value, fmt)

    return wrapped


def _date(value: datetime.date | None) -> Lazy:
    def wrapped(fmt: str = "SHORT_DATE_FORMAT") -> str:
        if value is None:
            return ""
        return defaultfilters.date(value, fmt)

    return wrapped


def _time(value: datetime.time | None) -> Lazy:
    def wrapped(fmt: str = None) -> str:
        if value is None:
            return ""
        return defaultfilters.time(value, fmt)

    return wrapped


def ui_text_vars(event) -> dict[str, typing.Any]:
    return {
        "event.name": event.name,
        "event.start.date": _date(event.start_date),
        "event.end.date": _date(event.end_date),
        "event.homepage": event.home_page,
        "registration.end.datetime": _datetime(event.registration_end),
        "registration.end.date": _date(event.registration_end.date())
        if event.registration_end
        else "",
        "registration.end.time": _time(event.registration_end.time())
        if event.registration_end
        else "",
    }
