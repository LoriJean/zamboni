from gzip import GzipFile
import json
from StringIO import StringIO

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

import mock
from nose import SkipTest
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq

import mkt.site.tests
from mkt.commonplace.models import DeployBuildId


class CommonplaceTestMixin(mkt.site.tests.TestCase):

    @mock.patch('mkt.commonplace.views.fxa_auth_info')
    def _test_url(self, url, fxa_mock, url_kwargs=None):
        """Test that the given url can be requested, returns a 200, and returns
        a valid gzipped response when requested with Accept-Encoding over ssl.
        Return the result of a regular (non-gzipped) request."""
        fxa_mock.return_value = ('fakestate', 'http://example.com/fakeauthurl')

        if not url_kwargs:
            url_kwargs = {}
        res = self.client.get(url, url_kwargs, HTTP_ACCEPT_ENCODING='gzip',
            **{'wsgi.url_scheme': 'https'})
        eq_(res.status_code, 200)
        eq_(res['Content-Encoding'], 'gzip')
        eq_(sorted(res['Vary'].split(', ')),
            ['Accept-Encoding', 'Accept-Language', 'Cookie'])
        ungzipped_content = GzipFile('', 'r', 0, StringIO(res.content)).read()

        res = self.client.get(url, url_kwargs, **{'wsgi.url_scheme': 'https'})
        eq_(res.status_code, 200)
        eq_(sorted(res['Vary'].split(', ')),
            ['Accept-Encoding', 'Accept-Language', 'Cookie'])
        eq_(ungzipped_content, res.content)
        return res


class TestCommonplace(CommonplaceTestMixin):

    def test_fireplace_firefox_accounts(self):
        res = self._test_url('/server.html')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'fireplace')
        self.assertContains(res, 'splash.css')
        self.assertNotContains(res, 'login.persona.org/include.js')
        eq_(res['Cache-Control'], 'max-age=180')
        self.assertContains(res, 'fakestate')
        self.assertContains(res, 'http://example.com/fakeauthurl')

    def test_commbadge(self):
        res = self._test_url('/comm/')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'commbadge')
        self.assertNotContains(res, 'splash.css')
        eq_(res['Cache-Control'], 'max-age=180')

    @mock.patch('mkt.commonplace.views.fxa_auth_info')
    def test_transonic(self, mock_fxa):
        mock_fxa.return_value = ('fakestate', 'http://example.com/fakeauthurl')
        res = self._test_url('/curate/')
        self.assertTemplateUsed(res, 'commonplace/index.html')
        self.assertEquals(res.context['repo'], 'transonic')
        self.assertNotContains(res, 'splash.css')
        eq_(res['Cache-Control'], 'max-age=180')

    @mock.patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_region_not_included_in_fireplace_if_sim_info(self, mock_region):
        test_region = mock.Mock()
        test_region.slug = 'testoland'
        mock_region.return_value = test_region
        for url in ('/server.html?mccs=blah',
                    '/server.html?mcc=blah&mnc=blah'):
            res = self._test_url(url)
            ok_('geoip_region' not in res.context, url)
            self.assertNotContains(res, 'data-region')

    @mock.patch('mkt.regions.middleware.RegionMiddleware.region_from_request')
    def test_region_included_in_fireplace_if_sim_info(self, mock_region):
        test_region = mock.Mock()
        test_region.slug = 'testoland'
        mock_region.return_value = test_region
        for url in ('/server.html?nativepersona=true',
                    '/server.html?mcc=blah',  # Incomplete info from SIM.
                    '/server.html',
                    '/server.html?'):
            res = self._test_url(url)
            self.assertEquals(res.context['geoip_region'], test_region)
            self.assertContains(res, 'data-region="testoland"')


class TestAppcacheManifest(CommonplaceTestMixin):

    def test_no_repo(self):
        if 'fireplace' not in settings.COMMONPLACE_REPOS_APPCACHED:
            raise SkipTest

        res = self.client.get(reverse('commonplace.appcache'))
        eq_(res.status_code, 404)

    def test_bad_repo(self):
        if 'fireplace' not in settings.COMMONPLACE_REPOS_APPCACHED:
            raise SkipTest

        res = self.client.get(reverse('commonplace.appcache'),
                              {'repo': 'transonic'})
        eq_(res.status_code, 404)

    @mock.patch('mkt.commonplace.views.get_build_id', new=lambda x: 'p00p')
    @mock.patch('mkt.commonplace.views.get_imgurls')
    def test_good_repo(self, get_imgurls_mock):
        if 'fireplace' not in settings.COMMONPLACE_REPOS_APPCACHED:
            raise SkipTest

        img = '/media/img/icons/eggs/h1.gif'
        get_imgurls_mock.return_value = [img]
        res = self._test_url(reverse('commonplace.appcache'),
                             {'repo': 'fireplace'})
        eq_(res.status_code, 200)
        assert '# BUILD_ID p00p' in res.content
        img = img.replace('/media/', '/media/fireplace/')
        assert img + '\n' in res.content


class TestIFrames(CommonplaceTestMixin):
    def setUp(self):
        self.iframe_install_url = reverse('commonplace.iframe-install')
        self.potatolytics_url = reverse('commonplace.potatolytics')

    @override_settings(DOMAIN='marketplace.firefox.com')
    def test_basic(self):
        res = self._test_url(self.iframe_install_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.marketplace.firefox.com',
             'app://marketplace.firefox.com',
             'https://marketplace.firefox.com',
             'app://tarako.marketplace.firefox.com',
             'https://hello.firefox.com',
             'https://call.firefox.com'])

        res = self._test_url(self.potatolytics_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.marketplace.firefox.com',
             'app://marketplace.firefox.com',
             'https://marketplace.firefox.com',
             'app://tarako.marketplace.firefox.com'])

    @override_settings(DOMAIN='marketplace.allizom.org')
    def test_basic_stage(self):
        res = self._test_url(self.iframe_install_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.marketplace.allizom.org',
             'app://marketplace.allizom.org',
             'https://marketplace.allizom.org',
             'app://tarako.marketplace.allizom.org',
             'https://hello.firefox.com',
             'https://call.firefox.com'])

        res = self._test_url(self.potatolytics_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.marketplace.allizom.org',
             'app://marketplace.allizom.org',
             'https://marketplace.allizom.org',
             'app://tarako.marketplace.allizom.org'])

    @override_settings(DOMAIN='marketplace-dev.allizom.org')
    def test_basic_dev(self):
        res = self._test_url(self.iframe_install_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.marketplace-dev.allizom.org',
             'app://marketplace-dev.allizom.org',
             'https://marketplace-dev.allizom.org',
             'app://tarako.marketplace-dev.allizom.org',
             'http://localhost:8675',
             'https://localhost:8675',
             'http://localhost',
             'https://localhost',
             'http://mp.dev',
             'https://mp.dev',
             'https://hello.firefox.com',
             'https://call.firefox.com',
             'https://loop-webapp-dev.stage.mozaws.net'])

        res = self._test_url(self.potatolytics_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.marketplace-dev.allizom.org',
             'app://marketplace-dev.allizom.org',
             'https://marketplace-dev.allizom.org',
             'app://tarako.marketplace-dev.allizom.org',
             'http://localhost:8675',
             'https://localhost:8675',
             'http://localhost',
             'https://localhost',
             'http://mp.dev',
             'https://mp.dev'])

    @override_settings(DOMAIN='example.com', DEBUG=True)
    def test_basic_debug_true(self):
        res = self._test_url(self.iframe_install_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.example.com',
             'app://example.com',
             'https://example.com',
             'app://tarako.example.com',
             'http://localhost:8675',
             'https://localhost:8675',
             'http://localhost',
             'https://localhost',
             'http://mp.dev',
             'https://mp.dev',
             'https://hello.firefox.com',
             'https://call.firefox.com',
             'https://loop-webapp-dev.stage.mozaws.net'])

        res = self._test_url(self.potatolytics_url)
        allowed_origins = json.loads(res.context['allowed_origins'])
        eq_(allowed_origins,
            ['app://packaged.example.com',
             'app://example.com',
             'https://example.com',
             'app://tarako.example.com',
             'http://localhost:8675',
             'https://localhost:8675',
             'http://localhost',
             'https://localhost',
             'http://mp.dev',
             'https://mp.dev'])


class TestOpenGraph(mkt.site.tests.TestCase):

    def _get_tags(self, res):
        """Returns title, image, description."""
        doc = pq(res.content)
        return (doc('[property="og:title"]').attr('content'),
                doc('[property="og:image"]').attr('content'),
                doc('[name="description"]').attr('content'))

    def test_basic(self):
        res = self.client.get(reverse('commonplace.fireplace'))
        title, image, description = self._get_tags(res)
        eq_(title, 'Firefox Marketplace')
        ok_(description.startswith('The Firefox Marketplace is'))

    def test_detail(self):
        app = mkt.site.tests.app_factory(description='Awesome')
        res = self.client.get(reverse('detail', args=[app.app_slug]))
        title, image, description = self._get_tags(res)
        eq_(title, app.name)
        eq_(image, app.get_icon_url(64))
        eq_(description, app.description)

    def test_detail_dne(self):
        res = self.client.get(reverse('detail', args=['DO NOT EXISTS']))
        title, image, description = self._get_tags(res)
        eq_(title, 'Firefox Marketplace')
        ok_(description.startswith('The Firefox Marketplace is'))


class TestBuildId(CommonplaceTestMixin):

    def test_build_id_from_db(self):
        DeployBuildId.objects.create(repo='fireplace', build_id='0118999')
        res = self._test_url('/server.html')
        doc = pq(res.content)

        scripts = doc('script')
        for script in scripts:
            src = pq(script).attr('src')
            if 'fireplace' in src:
                ok_(src.endswith('?b=0118999'))

    @mock.patch('mkt.commonplace.views.storage')
    def test_fallback_to_build_id_txt(self, storage_mock):
        storage_mock.open = mock.mock_open(read_data='0118999')

        res = self._test_url('/server.html')
        doc = pq(res.content)

        scripts = doc('script')
        for script in scripts:
            src = pq(script).attr('src')
            if 'fireplace' in src:
                ok_(src.endswith('?b=0118999'))
