# -*- coding: utf-8 -*-
from django import forms
from django.conf import settings
from django.utils import translation

from mock import patch
from nose.tools import eq_

from mkt.access.models import Group, GroupUser
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.ratings.models import Review
from mkt.users.models import UserEmailField, UserProfile
from mkt.webapps.models import AddonUser, Webapp


class TestUserProfile(TestCase):
    fixtures = fixture('webapp_337141', 'user_999')

    def test_anonymize(self):
        u = UserProfile.objects.get(pk=999)
        eq_(u.email, 'regular@mozilla.com')
        u.anonymize()
        x = UserProfile.objects.get(pk=999)
        eq_(x.email, None)

    def test_add_admin_powers(self):
        Group.objects.create(name='Admins', rules='*:*')
        u = UserProfile.objects.get(pk=999)

        assert not u.is_staff
        assert not u.is_superuser
        GroupUser.objects.create(group=Group.objects.filter(name='Admins')[0],
                                 user=u)
        assert u.is_staff
        assert u.is_superuser

    def test_dont_add_admin_powers(self):
        Group.objects.create(name='API', rules='API.Users:*')
        u = UserProfile.objects.get(pk=999)

        GroupUser.objects.create(group=Group.objects.get(name='API'),
                                 user=u)
        assert not u.is_staff
        assert not u.is_superuser

    def test_remove_admin_powers(self):
        Group.objects.create(name='Admins', rules='*:*')
        u = UserProfile.objects.get(pk=999)
        g = GroupUser.objects.create(group=Group.objects.get(name='Admins'),
                                     user=u)
        g.delete()
        assert not u.is_staff
        assert not u.is_superuser

    def test_review_replies(self):
        """
        Make sure that developer replies are not returned as if they were
        original reviews.
        """
        addon = Webapp.objects.get(id=337141)
        u = UserProfile.objects.get(pk=999)
        version = addon.current_version
        new_review = Review(version=version, user=u, rating=2, body='hello',
                            addon=addon)
        new_review.save()
        new_reply = Review(version=version, user=u, reply_to=new_review,
                           addon=addon, body='my reply')
        new_reply.save()

        review_list = [r.pk for r in u.reviews]

        eq_(len(review_list), 1)
        assert new_review.pk in review_list, (
            'Original review must show up in review list.')
        assert new_reply.pk not in review_list, (
            'Developer reply must not show up in review list.')

    def test_my_apps(self):
        """Test helper method to get N apps."""
        addon1 = Webapp.objects.create(name='test-1')
        AddonUser.objects.create(addon_id=addon1.id, user_id=999, listed=True)
        addon2 = Webapp.objects.create(name='test-2')
        AddonUser.objects.create(addon_id=addon2.id, user_id=999, listed=True)
        u = UserProfile.objects.get(id=999)
        addons = u.my_apps()
        self.assertTrue(sorted([a.name for a in addons]) == [addon1.name,
                                                             addon2.name])

    @patch.object(settings, 'LANGUAGE_CODE', 'en-US')
    def test_activate_locale(self):
        eq_(translation.get_language(), 'en-us')
        with UserProfile(username='yolo').activate_lang():
            eq_(translation.get_language(), 'en-us')

        with UserProfile(username='yolo', lang='fr').activate_lang():
            eq_(translation.get_language(), 'fr')


class TestUserEmailField(TestCase):
    fixtures = fixture('user_999')

    def test_success(self):
        user = UserProfile.objects.get(pk=999)
        eq_(UserEmailField().clean(user.email), user)

    def test_failure(self):
        with self.assertRaises(forms.ValidationError):
            UserEmailField().clean('xxx')

    def test_empty_email(self):
        UserProfile.objects.create(email='')
        with self.assertRaises(forms.ValidationError) as e:
            UserEmailField().clean('')
        eq_(e.exception.messages[0], 'This field is required.')
