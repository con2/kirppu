# -*- coding: utf-8 -*-
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils.translation import gettext as _

from .models import Event, Item, ItemType, ItemStateLog

__all__ = (
    "ItemCountData",
    "ItemEurosData",
    "iterate_logs",
    "RegistrationData",
    "SalesData",
)


# region Terse statistics generators.


class ItemCollectionData(object):
    """
    Collection of data for statistics, item states per item type or vendor.
    The sole argument to constructor decides which data set is represented on rows.
    A row can be retrieved with `data_set` function, which gives an instance of
    `ItemCollectionRow` used to iterate over the row.

    The query that is run will yield two-dimensional result (actually with all states, but no empty group_by's):

        [
        {'staged': 1, 'sum': 5, 'advertised': 3, 'sold': 1, 'itemtype': 2},
        {'staged': 0, 'sum': 2, 'advertised': 0, 'sold': 2, 'itemtype': 5},
        ...
        ]
    """

    PROPERTIES = OrderedDict((
        ('advertised', Item.ADVERTISED),
        ('brought', Item.BROUGHT),
        ('staged', Item.STAGED),
        ('sold', Item.SOLD),
        ('returned', Item.RETURNED),
        ('compensated', Item.COMPENSATED),
        ('sum', None),
    ))

    HIDDEN_PROPERTIES = OrderedDict((
        ("advertised_hidden", Item.ADVERTISED),
    ))

    ABANDONED_PROPERTIES = OrderedDict((
        ("brought_abandoned", Item.BROUGHT),
        ("staged_abandoned", Item.STAGED),
        ("sold_abandoned", Item.SOLD),
    ))

    _DEFAULT_VALUES = {
        p: 0
        for p in PROPERTIES.keys()
    }

    GROUP_ITEM_TYPE = "itemtype"
    GROUP_VENDOR = "vendor"

    def __init__(self, group_by, event: Event):
        self._group_by = group_by
        self._event = event
        self._raw_data = self._populate(Item.objects
                                        .using(self._event.get_real_database_alias())
                                        .filter(vendor__event=self._event)
                                        .values(group_by))

        if group_by == self.GROUP_ITEM_TYPE:
            self._init_for_item_type()
        elif group_by == self.GROUP_VENDOR:
            self._init_for_vendor()
        else:
            raise ValueError("Unknown group_by value")

    def _init_for_item_type(self):
        # Make the list data associative by item type.
        # The item type in raw_data is pk of ItemType.
        data = {
            row["itemtype"]: row
            for row in self._raw_data
        }

        # Add sum row. (Sum-column already exists.)
        # For optimization, this is done before filling gaps to avoid unnecessary calculations.
        sums = self._DEFAULT_VALUES.copy()
        for item_type, item_data in data.items():
            for property_key in self.PROPERTIES.keys():
                cell_value = item_data[property_key]
                if cell_value is None:
                    cell_value = 0
                    item_data[property_key] = cell_value
                sums[property_key] += cell_value

        # Fill possible gaps and order correctly.
        self._data = OrderedDict(
            (key, data.get(key, self._DEFAULT_VALUES))
            for key in ItemType.objects
                               .using(self._event.get_real_database_alias())
                               .filter(event=self._event)
                               .order_by("order")
                               .values_list("id", flat=True)
        )

        # Append calculated sum row.
        self._data["sum"] = sums

    def _init_for_vendor(self):
        # Order vendor data by their id.
        self._raw_data = self._raw_data.order_by("vendor_id")

        data = OrderedDict(
            (row["vendor"], row)
            for row in self._raw_data
        )
        self._data = data

    def data_set(self, key, name):
        """
        Return a data set / row from the collection.

        :param key: Data set key, such as item type or vendor id.
        :param name: Name for the data set.
        :return: Row containing the data.
        :rtype: ItemCollectionRow
        """
        raise NotImplementedError()

    def keys(self):
        return self._data.keys()

    def _populate(self, query):
        raise NotImplementedError()

    @classmethod
    def columns(cls):
        # XXX: This assumes subclasses of ItemCollectionRow follow these orders.
        return ["name"] + list(cls.PROPERTIES) + list(cls.ABANDONED_PROPERTIES) + list(cls.HIDDEN_PROPERTIES)

    def __repr__(self):
        return "{}({}, {})".format(self.__class__.__name__, self._group_by, self._data)


class ItemCollectionRow(object):
    """
    Base class for row data in `ItemCollectionData` mainly used for template to iterate over the row.
    """
    def __init__(self, key, data, name):
        self.key = key
        self.name = name
        self._data = data

    def __repr__(self):
        return "{}({}, {})".format(self.__class__.__name__, self.name, self._data)

    @property
    def property_values(self):
        for property_name in ItemCollectionData.PROPERTIES:
            yield self.fmt(self._data[property_name])

    @property
    def property_names(self):
        states = dict(Item.STATE)
        for property_name, property_state in ItemCollectionData.PROPERTIES.items():
            if property_name == "sum":
                yield _("Sum")
            else:
                yield states[property_state]

    @property
    def abandoned(self):
        for property_name in ItemCollectionData.ABANDONED_PROPERTIES:
            yield self.fmt(self._data[property_name])

    @property
    def hidden(self):
        for property_name in ItemCollectionData.HIDDEN_PROPERTIES:
            yield self.fmt(self._data[property_name])

    def fmt(self, value):
        raise NotImplementedError()

    def row_obj(self):
        r = [self.name]
        r.extend(self.property_values)
        r.extend(self.abandoned)
        r.extend(self.hidden)
        return r


def _state_queries(props, aggregate, condition, result, field):
    return {
        key: aggregate(models.Case(models.When(
            models.Q(state=p) & condition, then=result), output_field=field()))
        for key, p in props.items()
    }


class ItemCountData(ItemCollectionData):
    def _populate(self, query):
        # Count items per state. query must be already made group_by with query.values.
        states = {
            key: models.Count(models.Case(models.When(
                models.Q(state=p, hidden=False) if p == Item.ADVERTISED else models.Q(state=p),
                then=1), output_field=models.IntegerField()))
            for key, p in self.PROPERTIES.items()
            if p is not None
        }
        abandoned = _state_queries(
            self.ABANDONED_PROPERTIES, models.Count, models.Q(abandoned=True), 1, models.IntegerField)
        hidden = _state_queries(
            self.HIDDEN_PROPERTIES, models.Count, models.Q(hidden=True), 1, models.IntegerField)
        states.update(abandoned)
        states.update(hidden)
        # Return a result list that contains counts for all states, sum and the value for group_by per list item.
        return query.annotate(
            sum=models.Count("id"),
            **states
        )

    def data_set(self, key, name):
        return ItemCountRow(key, self._data[key], name)


class ItemCountRow(ItemCollectionRow):
    def fmt(self, value):
        return value


class ItemEurosData(ItemCollectionData):
    def __init__(self, *args, **kwargs):
        super(ItemEurosData, self).__init__(*args, **kwargs)
        self.use_cents = False

    def _populate(self, query):
        # Count item prices per state. query must be already made group_by with query.values.
        states = {
            key: models.Sum(models.Case(models.When(
                models.Q(state=p, hidden=False) if p == Item.ADVERTISED else models.Q(state=p),
                then=models.F("price")), output_field=models.DecimalField()))
            for key, p in self.PROPERTIES.items()
            if p is not None
        }
        abandoned = _state_queries(
            self.ABANDONED_PROPERTIES, models.Sum, models.Q(abandoned=True), models.F("price"), models.DecimalField)
        hidden = _state_queries(
            self.HIDDEN_PROPERTIES, models.Sum, models.Q(hidden=True), models.F("price"), models.DecimalField)
        states.update(abandoned)
        states.update(hidden)
        # Return a result list that contains prices for all states, sum and the value for group_by per list item.
        return query.annotate(
            sum=models.Sum("price"),
            **states
        )

    def data_set(self, key, name):
        return ItemEurosRow(self.use_cents, key, self._data[key], name)


class ItemEurosRow(ItemCollectionRow):
    def __init__(self, use_cents, *args, **kwargs):
        super(ItemEurosRow, self).__init__(*args, **kwargs)
        self._use_cents = use_cents
        self._currency = settings.KIRPPU_CURRENCY["html"]

    def fmt(self, value):
        if self._use_cents:
            # NB: This produces 99 from a value "0.999" whereas price_fmt_for produces 1.00...
            return int((value or 0) * 100)
        if value:
            processed = Item.price_fmt_for(value)
        else:
            processed = 0
        formatted_value = "{}{}{}".format(self._currency[0], processed, self._currency[1])
        return formatted_value


# endregion


########################


# region Statistics graphs generators.

class GraphLog(object):
    unix_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def __init__(self, event: Event, as_prices=False, extra_filter=None):
        self._event = event
        self._as_prices = as_prices
        self._filter = extra_filter or dict()

    def query(self, only):
        query = self._create_query().filter(item__vendor__event=self._event)
        query = query.filter(**self._filter)
        if self._as_prices:
            return query.only("item__price", *only).annotate(value=F("item__price"))
        return query.only(*only).annotate(value=models.Value(1, output_field=models.IntegerField()))

    @classmethod
    def datetime_to_js_time(cls, dt):
        return int((dt - cls.unix_epoch).total_seconds() * 1000)

    def get_log_str(self, bucket_time, balance):
        raise NotImplementedError

    def _create_query(self):
        raise NotImplementedError


class RegistrationData(GraphLog):
    advertised_status = (Item.ADVERTISED,)

    def _create_query(self):
        return ItemStateLog.objects.using(self._event.get_real_database_alias()).filter(new_state=Item.ADVERTISED)

    def get_log_str(self, bucket_time, balance):
        entry_time = self.datetime_to_js_time(bucket_time)
        advertised = sum(balance[status] for status in self.advertised_status)
        return '%d,%s\n' % (
            entry_time,
            advertised,
        )


class SalesData(GraphLog):
    brought_status = (Item.BROUGHT, Item.STAGED, Item.SOLD, Item.MISSING, Item.RETURNED, Item.COMPENSATED)
    unsold_status = (Item.BROUGHT, Item.STAGED)
    money_status = (Item.SOLD,)
    compensated_status = (Item.COMPENSATED, Item.RETURNED)

    def _create_query(self):
        return ItemStateLog.objects.using(self._event.get_real_database_alias()).exclude(new_state=Item.ADVERTISED)

    def get_log_str(self, bucket_time, balance):
        entry_time = self.datetime_to_js_time(bucket_time)
        brought = sum(balance[status] for status in self.brought_status)
        unsold = sum(balance[status] for status in self.unsold_status)
        money = sum(balance[status] for status in self.money_status)
        compensated = sum(balance[status] for status in self.compensated_status)
        return '%d,%s,%s,%s,%s\n' % (
            entry_time,
            brought,
            unsold,
            money,
            compensated,
        )


def iterate_logs(using):
    """ Iterate through ItemStateLog objects returning current sum of each type of object at each timestamp.

    Example of returned CVS: js_time, advertised, brought, unsold, money, compensated

    js_time is milliseconds from unix_epoch.
    advertised is the number of items registered to the event at any time.
    brought is the cumulative sum of all items brought to the event.
    unsold is the number of items physically at the event. Should approach zero by the end of the event.
    money is the number of sold items not yet redeemed by the seller. Should approach zero by the end of the event.
    compensated is the number of sold and unsold items redeemed by the seller. Should approach brought.

    :param using: GraphLog used to create the output.
    :type using: GraphLog
    :return: JSON presentation of the objects, one item at a time.

    """
    # Collect the data into buckets of size bucket_td to reduce the amount of data that has to be sent
    # and parsed at client side.
    balance = {item_type: 0 for item_type, _item_desc in Item.STATE}
    bucket_time = None
    bucket_td = timedelta(seconds=60)

    only = "old_state", "new_state", "time"
    entries = using.query(only)

    for entry in entries.order_by("time"):
        if bucket_time is None:
            bucket_time = entry.time
            # Start the graph before the first entry, such that everything starts at zero.
            yield using.get_log_str(bucket_time - bucket_td, balance)
        if (entry.time - bucket_time) > bucket_td:
            # Fart out what was in the old bucket and start a new bucket.
            yield using.get_log_str(bucket_time, balance)
            bucket_time = entry.time

        item_weight = entry.value

        if entry.old_state:
            balance[entry.old_state] -= item_weight
        balance[entry.new_state] += item_weight

    # Fart out the last bucket.
    if bucket_time is not None:
        yield using.get_log_str(bucket_time, balance)


# endregion
