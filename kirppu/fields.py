from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms.fields import Field, CharField
from django.utils.translation import gettext_lazy as _

import decimal
from decimal import Decimal, InvalidOperation
import re


class ItemPriceField(Field):

    default_error_messages = {
        'invalid': _('Price must be numeric.'),
        'required': _('Item must have a price.'),
        'min_value': _(u"Price too low. (min {} euros)"),
        'max_value': _(u"Price too high. (max {} euros)"),
    }

    def __init__(self, **kwargs):
        super(ItemPriceField, self).__init__(**kwargs)

    def to_python(self, value):
        value = super(ItemPriceField, self).to_python(value)
        if value in self.empty_values:
            return None

        value = value.replace(",", ".")
        try:
            value = Decimal(value).quantize(Decimal('0.10'), rounding=decimal.ROUND_UP)
        except InvalidOperation:
            raise ValidationError(self.error_messages['invalid'], code='invalid')

        # Round up to nearest 50 cents.
        remainder = value % Decimal('.50')
        if remainder > Decimal('0'):
            value += Decimal('.50') - remainder

        return value

    def validate(self, value):
        super(ItemPriceField, self).validate(value)
        _min, _max = settings.KIRPPU_MIN_MAX_PRICE
        if value < Decimal(_min):
            raise ValidationError(self.error_messages['min_value'].format(_min), code='min_value')
        if value > Decimal(_max):
            raise ValidationError(self.error_messages['max_value'].format(_max), code='max_value')


class SuffixField(Field):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("error_messages", dict())
        kwargs["error_messages"].setdefault(
            "max_items",
            _(u'Maximum of %(count)i items allowed by a single range statement.')
        )
        self.max_total = kwargs.pop("max_total", 100)
        self.add_empty = kwargs.pop("add_empty", True)
        super(SuffixField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        """
        Turn 'a b 1 3-4' to ['a', 'b', '1', '3', '4']

        :type value: str | unicode
        :rtype: list
        """
        if value is None:
            if self.add_empty:
                return [u""]
            return []
        words = value.split()
        result = []

        for word in words:
            # Handle the range syntax as a special case.
            match = re.match(r"(\d+)-(\d+)$", word)
            if match:
                # Turn '1-3' to ['1', '2', '3'] and so on
                left, right = map(int, match.groups())
                if abs(left - right) + 1 > self.max_total:
                    return None
                if left > right:
                    left, right = right, left
                result.extend(map(str, range(left, right + 1)))
            else:
                result.append(word)

        if self.add_empty and not result:
            result.append(u"")

        return result

    def validate(self, value):
        if value is None:
            raise ValidationError(self.error_messages['max_items'], params={"count": self.max_total})
        super(SuffixField, self).validate(value)


class StripField(CharField):
    def to_python(self, value):
        return value.strip()
