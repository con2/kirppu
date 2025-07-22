import datetime
from functools import wraps
from django.core.exceptions import PermissionDenied
import django.forms
from django.http.response import HttpResponseForbidden, HttpResponseBadRequest
from django.utils.functional import Promise
from django.utils.html import conditional_escape, format_html, mark_safe
from django.utils.translation import gettext as _
from django.utils import timezone

RFC8601DATETIME = "%Y-%m-%dT%H:%M:%S%z"
RFC8601DATE = "%Y-%m-%d"
TIME = "%H:%M:%S"
# RFC2822TIME = "%a, %d %b %Y %H:%M:%S %z"
MEM_TIMES = {}


def model_dict_fn(*args, **kwargs):
    """
    Return a function that will create dictionary by reading values from class instance.

        >>> class C(object):
        ...     def __init__(self):
        ...         self.a = 3
        ...     as_dict = model_dict_fn("a")
        ...     as_renamed = model_dict_fn(renamed="a")
        ...     as_called = model_dict_fn(multi=lambda self: self.a * 2)
        >>> C().as_dict(), C().as_renamed(), C().as_called()
        ({'a': 3}, {'renamed': 3}, {'multi': 6})

    :param args: List of fields.
    :param kwargs: Fields to be renamed or overridden with another function call.
    :return: Function.
    """
    access = kwargs.pop("__access_fn", lambda self, value: getattr(self, value))
    extend = kwargs.pop("__extend", None)
    fields = {}
    if extend:
        fields.update(extend.fields)
    for plain_key in args:
        fields[plain_key] = plain_key
    fields.update(kwargs)

    def model_dict(self, exclude=None):
        """
        Get model fields as dictionary (for JSON/AJAX usage). Fields returned:
        {0}
        """
        exclude = exclude or ()
        ret = {}
        for key, value in fields.items():
            if key in exclude:
                continue
            if callable(value):
                ret[key] = value(self)
            elif value is None:
                if value in ret:
                    del ret[value]
            else:
                ret[key] = access(self, value)
                if callable(ret[key]):
                    ret[key] = ret[key]()
        return ret
    model_dict.__doc__ = model_dict.__doc__.format(", ".join(fields.keys()))
    model_dict.fields = fields  # "Base" field dictionary for extend.
    return model_dict


def format_datetime(dt):
    """
    Format given datetime in RFC8601 format, that is used with moment.js.

    :param dt: Datetime to format.
    :type dt: datetime.datetime|datetime.date|datetime.time
    :return: Formatted string.
    :rtype: str
    :raises RuntimeError: If input type is not understood.
    """
    if isinstance(dt, datetime.datetime):
        result = dt.strftime(RFC8601DATETIME)
    elif isinstance(dt, datetime.date):
        result = dt.strftime(RFC8601DATE)
    elif isinstance(dt, datetime.time):
        result = dt.strftime(TIME)
    else:
        raise RuntimeError("Unsupported object given for format_datetime: " + repr(dt))
    return result


class StaticTextWidget(django.forms.widgets.Widget):
    """
    Static text-field widget. Text should be set with set_text().
    Otherwise, `initial`-text is used, or empty string as fallback.
    The resulting text is rendered instead of any widget.
    """
    def __init__(self, **kwargs):
        super(StaticTextWidget, self).__init__(**kwargs)
        self._static_text = None

    def set_text(self, text):
        self._static_text = text

    def has_text(self):
        return self._static_text is not None

    def render(self, name, value, attrs=None, renderer=None):
        if isinstance(self._static_text or value, (list, tuple)):
            return mark_safe("".join(conditional_escape(p) for p in (self._static_text or value)))
        return self._static_text or value or ""


class ButtonWidget(StaticTextWidget):
    def __init__(self, **kwargs):
        self._click = kwargs.pop("click", None)
        super(ButtonWidget, self).__init__(**kwargs)

    def set_click(self, click):
        self._click = click

    def render(self, name, value, attrs=None, renderer=None):
        return format_html('<button type="button" onclick="{0}">{1}</button>',
            self._click,
            self._static_text or value or "",
        )


class StaticText(django.forms.CharField):
    """
    Static text-field using StaticTextWidget. Only required parameter is `text`.
    Other parameters as per `CharField`.
    """
    def __init__(self, text, **kwargs):
        kwargs.setdefault("widget", StaticTextWidget)
        kwargs["required"] = False
        super(StaticText, self).__init__(**kwargs)

        if isinstance(self.widget, StaticTextWidget) and not self.widget.has_text():
            self.widget.set_text(text)


def require_setting(setting, value):
    """
    Decorator that requires a setting in settings to be a certain value before continuing to the view.

    :param setting: Setting key to find from settings.
    :type setting: str
    :param value: Accepted value, or one-argument callable returning True if accepted and False otherwise.
    :type value: T | callable
    :return: View decorator that will test the specified setting.
    """
    def decorator(fn):
        from django.conf import settings
        callback = callable(value)

        @wraps(fn)
        def inner(request, *args, **kwargs):
            current_value = getattr(settings, setting, None)
            if not ((not callback and current_value == value) or (callback and value(current_value))):
                raise PermissionDenied()
            return fn(request, *args, **kwargs)
        return inner
    return decorator


def is_vendor_open(request, event):
    """
    Test if Item edit for vendor is currently open.

    :param request: Optional Django request for checking whether current user has override permission for registration.
    :type event: Event
    :return: True if open, False if not and modifications by vendor must not be allowed.
    """
    end = event.registration_end
    from .models import EventPermission
    return (end is not None and timezone.now() <= end and not event.registration_disabled) or (
        EventPermission.get(event, request.user).can_register_items_outside_registration
    )


def is_registration_closed_for_users(event):
    if event.registration_disabled:
        return True
    end = event.registration_end
    if end is None:
        return True
    return timezone.now() > end


def require_vendor_open(fn):
    """
    Decorate (view) function so that it will return Forbidden if Item edit for vendor is not open.

    :param fn: Function to decorate.
    :return: Decorated function.
    """
    @wraps(fn)
    def inner(request, event_slug, *args, **kwargs):
        from .models import Event
        event = Event.objects.get(slug=event_slug)
        if not is_vendor_open(request, event=event):
            return HttpResponseForbidden(_(u"Registration is closed"))
        return fn(request, event, *args, **kwargs)
    return inner


def barcode_view(fn):
    """
    Decorator for views that render bar-codes. This will select image format, and on failure, return BadRequest.

    :param fn: Function to decorate. Function will get extra keyword argument `bar_type` containing the image format
        name.
    :return: Decorated function.
    """
    @wraps(fn)
    def inner(request, *args, **kwargs):
        default_format = 'png'
        bar_type = request.GET.get("format", default_format).lower()

        # Pubcode supports only these formats.
        if bar_type not in ('png', 'bmp'):
            return HttpResponseBadRequest(_(u"Image extension not supported"))

        kwargs["bar_type"] = bar_type
        return fn(request, *args, **kwargs)
    return inner


def short_description(text: str | Promise):
    """
    Decorator for property functions (or other functions) adding short_description to the function.

    :param text: Text to add.
    """
    def wrap(fn):
        fn.short_description = text
        return fn
    return wrap


def datetime_iso_human(dt):
    """Kind of ISO format, but slightly more readable, perhaps."""
    if dt is None:
        return None
    return (timezone.template_localtime(dt)
            .isoformat(timespec="milliseconds")
            .replace("T", " T ")
            .replace("+", " +")
            )
