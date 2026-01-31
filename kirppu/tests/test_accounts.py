# -*- coding: utf-8 -*-

from decimal import Decimal

from django.conf import settings
from django.test import TestCase, override_settings

from ..models import Account
from . import ResultMixin
from .api_access import Api
from .factories import ClerkFactory, CounterFactory, EventFactory, EventPermissionFactory


@override_settings(LANGUAGES=(("en", "English"),))
class TestAccounts(TestCase, ResultMixin):
    def setUp(self) -> None:
        self.client.cookies.load({settings.LANGUAGE_COOKIE_NAME: 'en'})

        self.commit = True  # Overridden in Pretend subclass.
        self.event = EventFactory.create()
        self.clerk = ClerkFactory.create(event=self.event)
        EventPermissionFactory(event=self.event, user=self.clerk.user, can_perform_overseer_actions=True)

        self.counter = CounterFactory.create(event=self.event)
        self.api = Api(client=self.client, event=self.event)
        self.default = Account.objects.create(
            event=self.event,
            name="Default",
        )
        self.second = Account.objects.create(
            event=self.event,
            name="Other",
        )

    def login(self):
        self.assertSuccess(self.api.clerk_login(code=self.clerk.get_code(), counter=self.counter.private_key))

    def assertDefaultBalance(self, expect: Decimal):
        actual = Account.objects.get(pk=self.default.pk).balance
        if self.commit:
            self.assertEqual(expect, actual)
        else:
            self.assertEqual(self.default.balance, actual)

    def assertSecondBalance(self, expect: Decimal):
        actual = Account.objects.get(pk=self.second.pk).balance
        if self.commit:
            self.assertEqual(expect, actual)
        else:
            self.assertEqual(self.second.balance, actual)

    def test_regular_clerk_cannot_authorize(self):
        self.login()  # Logged in to overseer with required access.
        self.default.balance = Decimal(50)
        self.default.save()

        # Regular user cannot authorize transfer.
        regular = ClerkFactory.create(event=self.event)

        def doit():
            self.assertContains(self.api.transfer_money(
                src_id=self.default.pk,
                dst_id=self.second.pk,
                amount=Decimal(5),
                note="",
                auth=regular.access_code,
                commit="1" if self.commit else "",
            ), "have permission", status_code=403)
        doit()

        # This shouldn't matter.
        EventPermissionFactory(event=self.event, user=regular.user)
        doit()

    def test_same_account(self):
        self.login()
        self.default.balance = Decimal(50)
        self.default.save()

        self.assertContains(self.api.transfer_money(
            src_id=self.default.pk,
            dst_id=self.default.pk,
            amount=Decimal(5),
            note="",
            auth=self.clerk.access_code,
            commit="1" if self.commit else "",
        ), "cannot be the same", status_code=400)

    def test_negative_amount(self):
        self.login()
        self.default.balance = Decimal(50)
        self.default.save()

        self.assertContains(self.api.transfer_money(
            src_id=self.default.pk,
            dst_id=self.second.pk,
            amount=Decimal(-5),
            note="",
            auth=self.clerk.access_code,
            commit="1" if self.commit else "",
        ), "must be positive", status_code=400)

    def test_transfer(self):
        self.login()
        self.default.balance = Decimal(50)
        self.default.save()

        self.assertSuccess(self.api.transfer_money(
            src_id=self.default.pk,
            dst_id=self.second.pk,
            amount=Decimal(5),
            note="",
            auth=self.clerk.access_code,
            commit="1" if self.commit else "",
        ))
        self.assertSuccess(self.api.transfer_money(
            src_id=self.default.pk,
            dst_id=self.second.pk,
            amount=Decimal(45),
            note="",
            auth=self.clerk.access_code,
            commit="1" if self.commit else "",
        ))
        self.assertDefaultBalance(Decimal(0))

    def test_balance_not_negative(self):
        self.login()
        self.default.balance = Decimal(50)
        self.default.save()

        ret = self.api.transfer_money(
            src_id=self.default.pk,
            dst_id=self.second.pk,
            amount=Decimal(51),
            note="",
            auth=self.clerk.access_code,
            commit="1" if self.commit else "",
        )
        if self.commit:
            self.assertContains(ret, "balance", status_code=409)
        else:
            self.assertSuccess(ret)
        self.assertDefaultBalance(Decimal(50))

    def test_loan(self):
        self.login()
        self.default.allow_negative_balance = True
        self.default.save()

        manager = ClerkFactory.create(event=self.event)
        EventPermissionFactory(event=self.event, user=manager.user,
                               can_perform_overseer_actions=True, can_manage_event=True)

        def with_clerk(clerk):
            return self.api.transfer_money(
                src_id=self.default.pk,
                dst_id=self.second.pk,
                amount=Decimal(50),
                note="",
                auth=clerk.access_code,
                commit="1" if self.commit else "",
            )

        self.assertContains(with_clerk(self.clerk), "manage permission", status_code=403)
        self.assertSuccess(with_clerk(manager))

        self.assertDefaultBalance(Decimal(-50))
        self.assertSecondBalance(Decimal(50))

    def test_return_loan(self):
        self.login()
        self.default.allow_negative_balance = True
        self.default.balance = Decimal(-50)
        self.default.save()

        self.second.balance = Decimal(50)
        self.second.save()

        self.assertSuccess(self.api.transfer_money(
            src_id=self.second.pk,
            dst_id=self.default.pk,
            amount=Decimal(50),
            note="",
            auth=self.clerk.access_code,
            commit="1" if self.commit else "",
        ))
        self.assertDefaultBalance(Decimal(0))
        self.assertSecondBalance(Decimal(0))


class TestAccountsPretend(TestAccounts):
    def setUp(self) -> None:
        super().setUp()
        self.commit = False
