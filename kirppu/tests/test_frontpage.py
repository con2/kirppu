# -*- coding: utf-8 -*-

from django.test import TestCase
from django.utils.timezone import now, timedelta

from ..models import Event
from . import ResultMixin
from .factories import EventFactory


class _Base(TestCase, ResultMixin):
    NO_CURRENT_EVENTS = 'id="events_no_future"'
    CURRENT_EVENT_ATTR = 'data-currentevent'
    CURRENT_EVENT = CURRENT_EVENT_ATTR + '="%s"'  # In "Current events" -list.
    ONGOING_EVENT = 'data-ongoingevent="%s"'
    OLD_EVENT_ATTR = 'data-oldevent'
    OLD_EVENT = OLD_EVENT_ATTR + '="%s"'

    @staticmethod
    def _make_old_event(start_days=10):
        _now = now()
        return EventFactory(
            start_date=_now - timedelta(days=start_days),
            end_date=_now - timedelta(days=start_days - 1),
            registration_end=_now - timedelta(days=start_days + 2))


class FrontPageTest(_Base):
    def test_redirect(self):
        result = self.client.get("/", follow=True)
        self.assertRedirects(result, "/kirppu/")

    def test_empty(self):
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)

    def test_single_event(self):
        event = EventFactory.create()
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.CURRENT_EVENT % event.slug)

    def test_ongoing_event(self):
        event = self._make_old_event(1)
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.ONGOING_EVENT % event.slug)

    def test_old_event(self):
        event = self._make_old_event()
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)
        self.assertContains(result, self.OLD_EVENT % event.slug)

    def test_new_and_old_event(self):
        event = EventFactory.create()
        old_event = self._make_old_event()
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.CURRENT_EVENT % event.slug)
        self.assertContains(result, self.OLD_EVENT % old_event.slug)
        self.assertNotContains(result, self.NO_CURRENT_EVENTS)

    def test_very_old_event(self):
        event = self._make_old_event(200)
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)
        self.assertNotContains(result, self.OLD_EVENT_ATTR)
        self.assertNotContains(result, self.CURRENT_EVENT_ATTR)

    def test_hidden_event(self):
        event = EventFactory.create(visibility=Event.VISIBILITY_NOT_LISTED)
        result = self.assertSuccess(self.client.get("/kirppu/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)
        self.assertNotContains(result, self.OLD_EVENT_ATTR)
        self.assertNotContains(result, self.CURRENT_EVENT_ATTR)


class MobileFrontPageTest(_Base):
    def test_empty(self):
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)

    def test_single_event(self):
        event = EventFactory.create()
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.CURRENT_EVENT % event.slug)

    def test_ongoing_event(self):
        event = self._make_old_event(1)
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.ONGOING_EVENT % event.slug)

    def test_old_event(self):
        event = self._make_old_event()
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)
        self.assertNotContains(result, self.OLD_EVENT_ATTR)

    def test_new_and_old_event(self):
        event = EventFactory.create()
        old_event = self._make_old_event()
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.CURRENT_EVENT % event.slug)
        self.assertNotContains(result, self.OLD_EVENT_ATTR)
        self.assertNotContains(result, self.NO_CURRENT_EVENTS)

    def test_very_old_event(self):
        event = self._make_old_event(200)
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)
        self.assertNotContains(result, self.OLD_EVENT_ATTR)
        self.assertNotContains(result, self.CURRENT_EVENT_ATTR)

    def test_hidden_event(self):
        event = EventFactory.create(visibility=Event.VISIBILITY_NOT_LISTED)
        result = self.assertSuccess(self.client.get("/m/"))
        self.assertContains(result, self.NO_CURRENT_EVENTS)
        self.assertNotContains(result, self.OLD_EVENT_ATTR)
        self.assertNotContains(result, self.CURRENT_EVENT_ATTR)
