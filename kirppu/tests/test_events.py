# -*- coding: utf-8 -*-
from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings

from . import ResultMixin
from .factories import (
    ApiItemFactory,
    ApiBoxFactory,
    EventFactory,
    ItemTypeFactory,
    UserFactory,
    VendorFactory,
)

_NOT_SET = object()


@override_settings(LANGUAGES=(("en", "English"),))
class RegistrationTest(TestCase, ResultMixin):
    def setUp(self) -> None:
        self.user = UserFactory.create()

        self.client.force_login(self.user)

        self.d_before = datetime.fromisoformat("2026-03-01T10:00:00+00:00")
        self.d_start = datetime.fromisoformat("2026-03-01T12:00:00+00:00")
        self.d_between = datetime.fromisoformat("2026-03-01T18:00:00+00:00")
        self.d_end = datetime.fromisoformat("2026-03-02T12:00:00+00:00")
        self.d_after = datetime.fromisoformat("2026-03-02T14:00:00+00:00")

    def _init(
        self,
        registration_start=_NOT_SET,
        registration_end=_NOT_SET,
        registration_disabled=False,
    ) -> tuple[dict, dict]:
        self.event = EventFactory.create(
            registration_start=self.d_start
            if registration_start is _NOT_SET
            else registration_start,
            registration_end=self.d_end
            if registration_end is _NOT_SET
            else registration_end,
            registration_disabled=registration_disabled,
        )
        self.type = ItemTypeFactory.create(event=self.event)
        self.vendor = VendorFactory.create(event=self.event, user=self.user)
        return (
            ApiItemFactory.create(item_type=self.type.id, price="1.00"),
            ApiBoxFactory.create(item_type=self.type.id, price="1.00"),
        )

    @property
    def _item_url(self) -> str:
        return "/kirppu/%s/vendor/item/" % self.event.slug

    @property
    def _box_url(self) -> str:
        return "/kirppu/%s/vendor/box/" % self.event.slug

    def test_in_time_range_disabled(self) -> None:
        item, box = self._init(registration_disabled=True)
        with patch("kirppu.models.tz_now", return_value=self.d_between):
            self.assertResult(self.client.post(self._item_url, data=item), expect=403)
            self.assertResult(self.client.post(self._box_url, data=box), expect=403)

    def test_in_time_range(self) -> None:
        item, box = self._init()
        with patch("kirppu.models.tz_now", return_value=self.d_between) as p:
            self.assertSuccess(self.client.post(self._item_url, data=item))
            self.assertSuccess(self.client.post(self._box_url, data=box))
            p.assert_called()

    def test_before_time_range(self) -> None:
        item, box = self._init()
        with patch("kirppu.models.tz_now", return_value=self.d_before):
            self.assertResult(self.client.post(self._item_url, data=item), expect=403)
            self.assertResult(self.client.post(self._box_url, data=box), expect=403)

    def test_after_time_range(self) -> None:
        item, box = self._init()
        with patch("kirppu.models.tz_now", return_value=self.d_after):
            self.assertResult(self.client.post(self._item_url, data=item), expect=403)
            self.assertResult(self.client.post(self._box_url, data=box), expect=403)

    def test_after_start_open_end(self) -> None:
        item, box = self._init(registration_end=None)
        with patch("kirppu.models.tz_now", return_value=self.d_after):
            self.assertSuccess(self.client.post(self._item_url, data=item))
            self.assertSuccess(self.client.post(self._box_url, data=box))

    def test_before_end_open_start(self) -> None:
        item, box = self._init(registration_start=None)
        with patch("kirppu.models.tz_now", return_value=self.d_before):
            self.assertSuccess(self.client.post(self._item_url, data=item))
            self.assertSuccess(self.client.post(self._box_url, data=box))

    def test_open_range(self) -> None:
        item, box = self._init(registration_start=None, registration_end=None)
        with patch("kirppu.models.tz_now", return_value=self.d_before):
            self.assertSuccess(self.client.post(self._item_url, data=item))
            self.assertSuccess(self.client.post(self._box_url, data=box))
        with patch("kirppu.models.tz_now", return_value=self.d_after):
            self.assertSuccess(self.client.post(self._item_url, data=item))
            self.assertSuccess(self.client.post(self._box_url, data=box))
