# -*- coding: utf-8 -*-
from django.test import TestCase, override_settings

from . import ResultMixin
from ..models import Event, EventPermission
from .factories import EventPermissionFactory, UserFactory, EventFactory


@override_settings(LANGUAGES=(("en", "English"),))
class SubmitTest(TestCase, ResultMixin):
    def setUp(self):
        self.event: Event = EventFactory(access_signup=True)
        self.clerk_user = UserFactory()

        self.manager = UserFactory()
        self.manager_perm: EventPermission = EventPermissionFactory(
            event=self.event,
            user=self.manager,
            can_manage_event=True,
        )
        self.client.force_login(self.clerk_user)

    def test_usual(self):
        self.assertResult(self.client.post(
            f"/kirppu/{self.event.slug}/signup",
            {
                "t_clerk": 1,
            }
        ), expect=302)

        self.client.force_login(self.manager)
        self.assertSuccess(self.client.get(
            f"/kirppu/{self.event.slug}/manage/people"
        ))

    def test_no_targets(self):
        self.assertResult(self.client.post(
            f"/kirppu/{self.event.slug}/signup",
            {
                "message": ".",
            }
        ), expect=302)

        self.client.force_login(self.manager)
        self.assertSuccess(self.client.get(
            f"/kirppu/{self.event.slug}/manage/people"
        ))

