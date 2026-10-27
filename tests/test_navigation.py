"""Navigation and engine discovery regressions; only disposable account storage.

Run with the existing suite: python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

_storage = tempfile.TemporaryDirectory(prefix='nav12-navigation-test-')
os.environ['DATA_DIR'] = _storage.name
os.environ['DATABASE_URL'] = os.environ.get('NAV12_TEST_DATABASE_URL', 'sqlite:///' + str(Path(_storage.name) / 'test.sqlite3'))
os.environ['APP_ENV'] = 'development'

from app import app
from collection import BRANDS, CARS, ENGINES


class Markup(HTMLParser):
    """Collect semantic hooks without requiring an HTML parsing dependency."""

    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def with_class(self, class_name):
        return [(tag, attrs) for tag, attrs in self.tags
                if class_name in attrs.get('class', '').split()]

    def card_slugs(self):
        return {attrs['href'].removeprefix('/cars/') for _, attrs in
                self.with_class('nv-card-link')}


EXPECTED = {
    'na-v12': {'ferrari-812-superfast', 'lamborghini-revuelto'},
    'twin-turbo-v12': set(),
    'v12': {'ferrari-812-superfast', 'lamborghini-revuelto'},
    'v10': {'audi-r8-performance'},
    'v8': {'mercedes-amg-gt-63', 'mclaren-750s', 'aston-martin-db12'},
    'v6': set(),
    'flat-six': {'porsche-911-gt3'},
    'inline-six': {'bmw-m4-competition'},
    'inline-four': set(),
    'w12': {'bentley-continental-gt-speed'},
    'w16': {'bugatti-chiron'},
    'naturally-aspirated': {'ferrari-812-superfast', 'lamborghini-revuelto',
                          'porsche-911-gt3', 'audi-r8-performance'},
    'turbocharged': {'mercedes-amg-gt-63', 'bmw-m4-competition', 'mclaren-750s',
                    'aston-martin-db12', 'bentley-continental-gt-speed', 'bugatti-chiron'},
    'supercharged': set(),
}


class NavigationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def member(self):
        with self.client.session_transaction() as session:
            session['username'] = 'NavigationTestDriver'

    def markup(self, route):
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200, route)
        return response, Markup(response.get_data(as_text=True))

    def test_all_engine_routes_require_login(self):
        for route in ['/engines'] + [f'/engines/{slug}' for slug in ENGINES]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login', response.location)

    def test_taxonomy_and_vehicle_engine_fields_are_complete(self):
        self.assertEqual(set(ENGINES), set(EXPECTED))
        for slug, engine in ENGINES.items():
            with self.subTest(engine=slug):
                self.assertEqual(engine['slug'], slug)
                for field in ('name', 'group', 'description'):
                    self.assertTrue(engine[field], field)
        for slug, car in CARS.items():
            with self.subTest(car=slug):
                self.assertTrue(car['engine_layout'])
                self.assertTrue(car['induction'])

    def test_engine_guides_render_correct_cars_and_empty_guides(self):
        self.member()
        _, index = self.markup('/engines')
        index_links = {attrs.get('href') for tag, attrs in index.tags if tag == 'a'}
        for slug, expected in EXPECTED.items():
            with self.subTest(engine=slug):
                self.assertIn(f'/engines/{slug}', index_links)
                response, markup = self.markup(f'/engines/{slug}')
                self.assertEqual(markup.card_slugs(), expected)
                self.assertIn(ENGINES[slug]['name'], response.get_data(as_text=True))
                if not expected:
                    # Zero-car engine types remain informative, navigable guide pages.
                    self.assertTrue(markup.with_class('nv-empty'))
                    self.assertIn('href="/collection', response.get_data(as_text=True))

    def test_engine_filter_has_exact_membership_and_persists_selection(self):
        self.member()
        for slug, expected in EXPECTED.items():
            with self.subTest(engine=slug):
                response, markup = self.markup('/collection?' + urlencode({'engine': slug}))
                self.assertEqual(markup.card_slugs(), expected)
                self.assertIn(f'{len(expected)} of {len(CARS)} cars', response.get_data(as_text=True))
                self.assertTrue(any(tag == 'option' and attrs.get('value') == slug
                                    and 'selected' in attrs for tag, attrs in markup.tags))
                self.assertTrue(any(tag == 'select' and attrs.get('id') == 'engine-filter'
                                    and attrs.get('name') == 'engine' for tag, attrs in markup.tags))

    def test_engine_filter_composes_with_existing_filters(self):
        self.member()
        cases = [
            ({'engine': 'v8', 'character': 'Grand tourer'},
             {'mercedes-amg-gt-63', 'aston-martin-db12'}),
            ({'engine': 'na-v12', 'powertrain': 'Plug-in hybrid'}, {'lamborghini-revuelto'}),
            ({'engine': 'turbocharged', 'brand': 'bmw', 'q': 'M4'}, {'bmw-m4-competition'}),
            ({'engine': 'v8', 'brand': 'porsche'}, set()),
            ({'engine': 'v6'}, set()),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                _, markup = self.markup('/collection?' + urlencode(filters))
                self.assertEqual(markup.card_slugs(), expected)

    def test_unknown_engine_returns_empty_filter_and_404_guide_safely(self):
        self.member()
        attack = '<script>alert(1)</script>'
        for slug in ('unknown-engine', attack):
            with self.subTest(engine=slug):
                response, markup = self.markup('/collection?' + urlencode({'engine': slug}))
                self.assertEqual(markup.card_slugs(), set())
                self.assertIn(b'No cars match', response.data)
                self.assertNotIn(attack.encode(), response.data)
        response = self.client.get('/engines/unknown-engine')
        self.assertEqual(response.status_code, 404)
        self.assertIn(b'Explore the collection', response.data)

    def test_navigation_sections_and_search_shared_across_member_pages(self):
        self.member()
        routes = ['/dashboard', '/collection', '/engines', '/collection/credits']
        routes += [f'/brands/{slug}' for slug in BRANDS]
        routes += [f'/cars/{slug}' for slug in CARS]
        routes += [f'/engines/{slug}' for slug in ENGINES]
        for route in routes:
            with self.subTest(route=route):
                response, markup = self.markup(route)
                self.assertEqual(len(markup.with_class('nv-explore-nav')), 1)
                self.assertEqual(len(markup.with_class('nv-nav-track')), 1)
                menus = [(tag, attrs) for tag, attrs in markup.tags if 'data-explore-menu' in attrs]
                self.assertEqual(len(menus), 5)
                self.assertTrue(all(tag == 'details' and attrs.get('name') == 'explore'
                                    for tag, attrs in menus))
                self.assertIn('data-click-only', menus[-1][1])
                self.assertTrue(any(tag == 'input' and attrs.get('type') == 'search'
                                    and attrs.get('name') == 'q' for tag, attrs in markup.tags))
                self.assertEqual(len(markup.with_class('nv-brands')), 1)
                self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])


if __name__ == '__main__':
    unittest.main()
