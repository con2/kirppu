# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.db.models import Sum, Q, QuerySet

from .models import ReceiptExtraRow, Receipt, Item, ReceiptItem
from .provision_dsl import run

__author__ = 'codez'


class Provision(object):
    def __init__(self, vendor_id: int, provision_function: str, receipt=None, database=None):
        self._vendor_id = vendor_id
        self._database = database or "default"

        self._vendor_items = vendor_items = Item.objects.using(self._database).filter(vendor__id=vendor_id)

        # Amount of total provision based on sold (=sold/compensated) items.
        if receipt is None:
            total_compensation_items = vendor_items.filter(state__in=(Item.SOLD, Item.COMPENSATED))
        else:
            # Include already compensated items and items being compensated.
            # Items that are recently sold should not change the compensation WITHIN a receipt.
            query = Q(state=Item.COMPENSATED) | Q(receiptitem__receipt=receipt)
            total_compensation_items = vendor_items.filter(query).distinct()

        self._total_compensation_items = total_compensation_items
        self._receipt = receipt

        # Provision to be paid from current SOLD items.
        self._provision_result = None
        # Provision to be paid extra from COMPENSATED items, i.e. fixing a mistake in calculation.
        self._provision_fix_result = None

        self._provision_function = provision_function

        # Total value of provision calculated from SOLD/receipt + COMPENSATED items.
        self._total_provision = self._run_function()

        if self.has_provision:
            if receipt is None:
                self._sum_for_compensation = \
                    vendor_items.filter(state=Item.SOLD).aggregate(sum=Sum("price"))["sum"]
            else:
                self._sum_for_compensation = \
                    ReceiptItem.objects.using(self._database).filter(receipt=receipt, action=ReceiptItem.ADD) \
                                       .aggregate(sum=Sum("item__price"))["sum"]
            if self._sum_for_compensation is None:
                self._sum_for_compensation = Decimal(0)

    @property
    def has_provision(self):
        return self._total_provision is not None and self._total_provision != Decimal(0)

    @classmethod
    def run_function(cls, provision_function, sold_and_compensated) -> Optional[Decimal]:
        if provision_function is None or provision_function.strip() in ("", "null", "0"):
            return None
        if not getattr(settings, "KIRPPU_ALLOW_PROVISION_FUNCTIONS", False):
            raise SuspiciousOperation("Provision functions are not allowed.")

        _r = run(provision_function, sold_and_compensated=sold_and_compensated)

        assert _r is None or isinstance(_r, (Decimal, int)), "Value returned from function must be null or a number"
        return _r

    def _run_function(self, items: Optional[QuerySet] = None) -> Optional[Decimal]:
        q = items
        if items is None:
            q = self._total_compensation_items
        return self.run_function(self._provision_function, q)

    def _calculate_provision_information(self):
        """

        :return: Provision value for current items and provision fix for total.
        :rtype: (ReceiptExtraRow, ReceiptExtraRow)
        """
        extras = ReceiptExtraRow.objects.using(self._database).filter(
            type__in=(ReceiptExtraRow.TYPE_PROVISION, ReceiptExtraRow.TYPE_PROVISION_FIX),
            receipt__type=Receipt.TYPE_COMPENSATION,
            receipt__receiptitem__item__vendor_id=self._vendor_id,
        ).distinct()
        extras = extras.aggregate(extras_value=Sum("value"))
        previous_provisions = extras["extras_value"] or Decimal(0)

        # [      Sold      ][ Compensated ]
        # [provision_result]
        # [         provision(All)        ]

        # fix = fn(Compensated) - sum(receipts.provision*)
        # provision(Sold) = provision(All) - fn(Compensated)

        compensated_items = self._vendor_items.filter(state=Item.COMPENSATED)
        if self._receipt:
            # Due no state for staged for compensation, exclude current receipt from fix calculations.
            compensated_items = compensated_items.exclude(receipt=self._receipt)
        fn_compensated = self._run_function(compensated_items)

        self._provision_fix_result = fn_compensated + previous_provisions  # previous_provisions is a negative value.
        self._provision_result = self._total_provision - fn_compensated

        if not compensated_items.exists() and self._provision_fix_result != Decimal(0):
            self._provision_result += self._provision_fix_result
            self._provision_fix_result = Decimal(0)

        # We present numbers in negative as the values are used in "how much would be given to vendor" context.
        self._provision_result = -self._provision_result
        self._provision_fix_result = -self._provision_fix_result

    def _ensure_result(self):
        if self._provision_result is None and self.has_provision:
            self._calculate_provision_information()

    @property
    def provision(self):
        """Provision to be paid (negative) from current SOLD/receipt items."""
        self._ensure_result()
        return self._provision_result

    @property
    def provision_fix(self):
        """Fix value to be paid (negative) due rounding errors or function adjustment."""
        self._ensure_result()
        return self._provision_fix_result

    def __str__(self):
        return "Provision(result={}, fix={}, total={})".format(
            self.provision, self.provision_fix, self._total_provision)
