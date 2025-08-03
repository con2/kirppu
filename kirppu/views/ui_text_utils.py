import datetime
import html
import typing

from django.conf import settings
from django.template import defaultfilters
from django.utils.timezone import is_naive, localtime

Lazy = typing.Callable[[str | None], str] | str


def _convert_localtime(value: datetime.datetime) -> datetime.datetime:
    if settings.USE_TZ and not is_naive(value):
        return localtime(value)
    return value


def _wrap(dt, value) -> str:
    return f'<time datetime="{html.escape(dt)}">{html.escape(value, quote=False)}</time>'


def _datetime(value: datetime.datetime | None) -> Lazy:
    def wrapped(fmt: str = "SHORT_DATETIME_FORMAT") -> str:
        if value is None:
            return ""
        local_value = _convert_localtime(value)
        dt = local_value.isoformat(timespec="minutes")
        return _wrap(dt, defaultfilters.date(local_value, fmt))

    return wrapped


def _date(value: datetime.date | None) -> Lazy:
    def wrapped(fmt: str = "SHORT_DATE_FORMAT") -> str:
        if value is None:
            return ""
        # datetime is a date.
        if isinstance(value, datetime.datetime):
            local_value = _convert_localtime(value)
            date = local_value.date()
            return _wrap(date.isoformat(), defaultfilters.date(date, fmt))
        else:
            return _wrap(value.isoformat(), defaultfilters.date(value, fmt))

    return wrapped


def _time(value: datetime.datetime | None) -> Lazy:
    def wrapped(fmt: str = None) -> str:
        if value is None:
            return ""
        local_value = _convert_localtime(value)
        time = local_value.time()
        return _wrap(time.isoformat(timespec="minutes"), defaultfilters.time(time, fmt))

    return wrapped


def ui_text_vars(event) -> dict[str, typing.Any]:
    return {
        "event.name": event.name,
        "event.start.date": _date(event.start_date),
        "event.end.date": _date(event.end_date),
        "event.homepage": event.home_page,
        "registration.end.datetime": _datetime(event.registration_end),
        "registration.end.date": _date(event.registration_end),
        "registration.end.time": _time(event.registration_end),
    }
