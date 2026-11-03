"""Engine Study integration checks using disposable development storage."""
import os
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

_storage = tempfile.TemporaryDirectory(prefix='nav12-engine-test-')
os.environ['DATA_DIR'] = _storage.name
os.environ['DATABASE_URL'] = os.environ.get(
    'NAV12_TEST_DATABASE_URL', 'sqlite:///' + str(Path(_storage.name) / 'test.sqlite3'))
os.environ['APP_ENV'] = 'development'

from app import app, account


class Scripts(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.sources = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.sources.append(dict(attrs).get('src'))


class EngineStudyTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def member(self):
        account('EngineStudyDriver', 'Test-password-2026')
        with self.client.session_transaction() as session:
            session['username'] = 'EngineStudyDriver'
            session['auth_version'] = app.extensions['recovery'].snapshot('EngineStudyDriver')['version']

    def test_engine_study_is_public_while_member_destinations_remain_protected(self):
        response = self.client.get('/engine')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'The V12 Engine Study', response.data)
        for route in ('/dashboard', '/collection', '/garage'):
            with self.subTest(route=route):
                member_response = self.client.get(route)
                self.assertEqual(member_response.status_code, 302)
                self.assertIn('/login', member_response.location)

    def test_engine_scripts_are_local_and_security_policy_remains_restricted(self):
        response = self.client.get('/engine')
        policy = response.headers['Content-Security-Policy']
        directives = {item.strip().split(' ', 1)[0]: item.strip() for item in policy.split(';') if item.strip()}
        self.assertEqual(directives['script-src'], "script-src 'self'")
        self.assertEqual(directives['object-src'], "object-src 'none'")
        self.assertEqual(directives['frame-ancestors'], "frame-ancestors 'none'")
        self.assertNotIn('unsafe-eval', policy)
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        sources = Scripts(response.get_data(as_text=True)).sources
        self.assertTrue(sources, 'Engine controls should load from a local script')
        self.assertTrue(all(source and source.startswith('/static/') for source in sources))
        self.assertIn("script-src 'none'", self.client.get('/healthz').headers['Content-Security-Policy'])

    def test_dashboard_invites_engine_exploration_and_preserves_collection(self):
        self.member()
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        for content in (b'href="/engine"', b'Explore the V12', b'engine/engine-teaser.webp',
                        b'href="/collection"', b'800 PS', b'The shortlist'):
            self.assertIn(content, response.data)
        self.assertNotIn(b'class="v12-pro"', response.data)

    def test_visitors_can_discover_engine_study_from_account_pages(self):
        for route in ('/login', '/signup'):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'href="/engine"', response.data)
                self.assertIn(b'Engine study', response.data)


if __name__ == '__main__':
    unittest.main()
