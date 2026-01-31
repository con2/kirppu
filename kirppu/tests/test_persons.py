from django.test import TestCase

from ..models import Vendor
from .factories import EventFactory, EventPermissionFactory, PersonFactory, UserFactory, VendorFactory


class _PersonTest(TestCase):
    event_creation_args = {}

    def setUp(self):
        self.user = UserFactory.create()
        self.event = EventFactory.create(**self.event_creation_args)
        self.vendor_id = ""  # empty string, as we don't have a vendor for this user.

    def _assertSelected(self, name, pk=""):
        resp = self.client.get("/kirppu/%s/" % self.event.slug)
        self.assertContains(resp, '<option value="new">')
        self.assertContains(resp, '<option value="{}" selected="selected">{}</option>'.format(pk, name))

    def _create(self, first_name="", last_name="", email="", phone=""):
        return self.client.post("/kirppu/%s/vendor/create" % self.event.slug, {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
        })

    def _createOtherUser(self, with_permission=True) -> Vendor:
        other = VendorFactory.create(event=self.event)
        if with_permission:
            EventPermissionFactory(event=self.event, user=other.user,
                                   can_create_sub_vendor=True,
                                   can_switch_sub_vendor=True)
        return other


class VendorSwitchWithoutSelfVendorTest(_PersonTest):
    event_creation_args = {"multiple_vendors_per_user": True}

    def setUp(self):
        super().setUp()
        EventPermissionFactory(event=self.event, user=self.user,
                               can_create_sub_vendor=True,
                               can_switch_sub_vendor=True)
        self.client.force_login(self.user)

    def test_defaultState(self):
        self._assertSelected(str(self.user), self.vendor_id)

    def test_createNew(self):
        new_id = self._create(first_name="John", last_name="Doe")
        vendors = Vendor.objects.filter(user=self.user, person__isnull=False, event=self.event)
        self.assertEqual(1, len(vendors))
        vendor = vendors[0]
        self.assertEqual(vendor.id, new_id)
        self.assertEqual(self.user, vendor.user)
        self.assertEqual("John", vendor.person.first_name)
        self.assertEqual("Doe", vendor.person.last_name)

        # We should still be in default state.
        self._assertSelected(str(self.user), self.vendor_id)

    def _create(self, first_name="", last_name="", email="", phone=""):
        resp = super()._create(first_name, last_name, email, phone).json()
        self.assertEqual("ok", resp["result"])
        return resp["id"]

    def test_switchToNew(self):
        new_id = self._create(first_name="John", last_name="Doe")
        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(new_id),
        })
        self.assertEqual(302, resp.status_code)
        self._assertSelected("John Doe", new_id)

    def test_switchBack(self):
        self.test_switchToNew()

        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(self.vendor_id),
        })
        self.assertEqual(302, resp.status_code)
        self._assertSelected(str(self.user), self.vendor_id)

    def test_switchToSelf(self):
        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(self.vendor_id),
        })
        self.assertEqual(302, resp.status_code)
        self._assertSelected(str(self.user), self.vendor_id)

    def test_switchOtherUser(self):
        # Vendor owned by other user
        other = self._createOtherUser(with_permission=True)
        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(other.id),
        })
        self.assertEqual(404, resp.status_code)
        self._assertSelected(str(self.user), self.vendor_id)

    def test_switchOtherPerson(self):
        # Person owned by other user
        person = PersonFactory.create()
        other = VendorFactory.create(event=self.event, person=person)
        EventPermissionFactory(event=self.event, user=other.user,
                               can_create_sub_vendor=True,
                               can_switch_sub_vendor=True)
        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(other.id),
        })
        self.assertEqual(404, resp.status_code)
        self._assertSelected(str(self.user), self.vendor_id)


class VendorSwitchTest(VendorSwitchWithoutSelfVendorTest):
    def setUp(self):
        super().setUp()
        self.vendor = VendorFactory.create(user=self.user, event=self.event)
        self.vendor_id = self.vendor.id


class VendorSwitchAnonymousTest(_PersonTest):
    def test_index(self):
        resp = self.client.get("/kirppu/%s/" % self.event.slug)
        self.assertEqual(200, resp.status_code)
        self.assertNotContains(resp, 'id="vendor-select-form"')


class VendorSwitchErrors1Test(_PersonTest):
    """Event not configured to use the feature."""
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _create(self, first_name="first_name", last_name="last_name", email="email", phone="phone"):
        return super()._create(first_name, last_name, email, phone)

    def test_create(self):
        resp = self._create()
        self.assertEqual(404, resp.status_code)
        self.assertEqual(0, Vendor.objects.all().count())

    def test_createWithPermission(self):
        # Should not matter that there is a permission, so test that too.
        EventPermissionFactory(event=self.event, user=self.user,
                               can_create_sub_vendor=True,
                               can_switch_sub_vendor=True)
        resp = self._create()
        self.assertEqual(404, resp.status_code)
        self.assertEqual(0, Vendor.objects.all().count())

    def test_switch(self):
        # Permissions for other user should not give rights for this user.
        other = self._createOtherUser(with_permission=True)
        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(other.id),
        })
        self.assertEqual(404, resp.status_code)


class VendorSwitchErrors2Test(_PersonTest):
    """Event configured, but user has no rights."""
    event_creation_args = {"multiple_vendors_per_user": True}

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def _create(self, first_name="first_name", last_name="last_name", email="email", phone="phone"):
        return super()._create(first_name, last_name, email, phone)

    def test_create(self):
        resp = self._create()
        self.assertEqual(403, resp.status_code)
        self.assertEqual(0, Vendor.objects.all().count())

    def test_switch(self):
        # Give other user permission, even though it should not matter.
        other = self._createOtherUser(with_permission=True)
        resp = self.client.post("/kirppu/%s/vendor/change" % self.event.slug, {
            "vendor": str(other.id),
        })
        self.assertEqual(403, resp.status_code)
