"""Garage isolation, persistence, rank integrity and authenticated form contracts."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from accounts import AccountStore, StorageUnavailable
from collection import CARS
from garage import GarageStore, favourites


# app.py initializes storage when imported. Always bootstrap it against a
# disposable database, even when this test file is run on its own from a shell
# containing production credentials. Keep this directory alive for the module.
_bootstrap_storage = tempfile.TemporaryDirectory(prefix='nav12-garage-bootstrap-')
with patch.dict(os.environ, {
    'APP_ENV': 'development',
    'DATA_DIR': _bootstrap_storage.name,
    'DATABASE_URL': 'sqlite:///' + str(Path(_bootstrap_storage.name) / 'bootstrap.sqlite3'),
}):
    from app import app as _app


class GarageTests(unittest.TestCase):
    def setUp(self):
        self.app = _app
        self.app.config['TESTING'] = True
        self.directory = tempfile.TemporaryDirectory(prefix='nav12-garage-test-')
        self.url = 'sqlite:///' + str(Path(self.directory.name) / 'test.sqlite3')
        self.accounts = AccountStore(self.url)
        self.accounts.initialize()
        self.store = GarageStore(self.accounts)
        self.store.initialize()
        self.accounts.create_account('GarageAlice', 'Alice-test-password')
        self.accounts.create_account('GarageBob', 'Bob-test-password')
        self.original_accounts = self.app.extensions['accounts']
        self.original_garage = self.app.extensions['garage']
        self.app.extensions['accounts'] = self.accounts
        self.app.extensions['garage'] = self.store
        self.client = self.app.test_client()
        self.slugs = list(CARS)[:5]
        self.login()

    def tearDown(self):
        self.app.extensions['accounts'] = self.original_accounts
        self.app.extensions['garage'] = self.original_garage
        self.accounts.close()
        self.directory.cleanup()

    def login(self, username='GarageAlice'):
        with self.client.session_transaction() as session:
            session.clear()
            session['username'] = username
            profile = self.app.extensions['recovery'].snapshot(username)
            session['auth_version'] = profile['version'] if profile else 0
            session['csrf_token'] = 'Garage-test-token'

    def post(self, action, slug, **data):
        return self.client.post(f'/garage/{action}/{slug}', data={'csrf_token': 'Garage-test-token', **data})

    def save(self, count=3):
        for slug in self.slugs[:count]:
            self.assertEqual(self.post('add', slug).status_code, 303)

    def test_save_is_idempotent_case_insensitive_and_persistent(self):
        self.save()
        self.store.add('garagealice', self.slugs[0])
        self.assertEqual(self.store.list_slugs('GARAGEALICE'), self.slugs[:3])
        other_accounts = AccountStore(self.url)
        try:
            other = GarageStore(other_accounts)
            other.initialize()
            self.assertEqual(other.list_slugs('GarageAlice'), self.slugs[:3])
            self.assertIsNotNone(other_accounts.read_hash('GarageAlice'))
        finally:
            other_accounts.close()

    def test_saved_cars_are_private_to_each_member(self):
        self.save()
        self.login('GarageBob')
        self.assertEqual(self.store.list_slugs('GarageBob'), [])
        self.assertEqual(self.post('remove', self.slugs[0]).status_code, 303)
        self.assertEqual(self.post('rank', self.slugs[0], position='1').status_code, 404)
        compare = '/garage/compare?' + '&'.join('car=' + s for s in self.slugs[:2])
        self.assertEqual(self.client.get(compare).status_code, 400)
        self.assertEqual(self.store.list_slugs('GarageAlice'), self.slugs[:3])

    def test_rank_reorders_and_removal_closes_gaps(self):
        self.save()
        self.assertEqual(self.post('rank', self.slugs[2], position='1').status_code, 303)
        self.assertEqual(self.store.list_slugs('GarageAlice'), [self.slugs[2], self.slugs[0], self.slugs[1]])
        self.assertEqual(self.post('remove', self.slugs[0]).status_code, 303)
        self.assertEqual(self.post('remove', self.slugs[0]).status_code, 303)
        with self.accounts.engine.connect() as connection:
            self.assertEqual(list(connection.scalars(select(favourites.c.rank).order_by(favourites.c.rank))), [1, 2])
        self.assertEqual(self.store.list_slugs('GarageAlice'), [self.slugs[2], self.slugs[1]])

    def test_invalid_ranks_and_unknown_cars_do_not_change_storage(self):
        self.save()
        for position in ('0', '-1', '4', 'abc', '', '1.5'):
            self.assertEqual(self.post('rank', self.slugs[0], position=position).status_code, 400)
        for action in ('add', 'remove', 'rank'):
            self.assertEqual(self.post(action, 'not-a-car', position='1').status_code, 404)
        self.assertEqual(self.store.list_slugs('GarageAlice'), self.slugs[:3])

    def test_compare_requires_two_to_four_distinct_owned_cars(self):
        self.save(5)
        for count in (2, 3, 4):
            response = self.client.get('/garage/compare', query_string=[('car', s) for s in self.slugs[:count]])
            self.assertEqual(response.status_code, 200)
            for slug in self.slugs[:count]:
                self.assertIn(CARS[slug]['name'].encode(), response.data)
        for slugs in ([], self.slugs[:1], self.slugs[:5], [self.slugs[0], self.slugs[0]], [self.slugs[0], 'unknown']):
            self.assertEqual(self.client.get('/garage/compare', query_string=[('car', s) for s in slugs]).status_code, 400)

    def test_garage_empty_and_saved_pages_render(self):
        self.assertEqual(self.client.get('/garage').status_code, 200)
        self.save()
        response = self.client.get('/garage')
        self.assertEqual(response.status_code, 200)
        for slug in self.slugs[:3]:
            self.assertIn(CARS[slug]['name'].encode(), response.data)
        self.assertIn(b'/garage/remove/', response.data)
        self.assertIn(b'/garage/rank/', response.data)
        self.assertIn(b'name="position"', response.data)
        self.assertIn(b'My Garage <span class="nv-garage-count">3</span>', response.data)
        collection = self.client.get('/collection')
        self.assertIn(b'nv-favourite-button is-saved', collection.data)
        self.assertIn(b'/garage/remove/', collection.data)

    def test_mutations_require_post_csrf_and_login(self):
        self.save()
        for action in ('add', 'remove', 'rank'):
            route = f'/garage/{action}/{self.slugs[0]}'
            self.assertEqual(self.client.get(route).status_code, 405)
            for token in ('', 'incorrect'):
                self.assertEqual(self.client.post(route, data={'csrf_token': token, 'position': '1'}).status_code, 400)
        with self.client.session_transaction() as session:
            session.pop('username')
        self.assertEqual(self.client.get('/garage').status_code, 302)
        self.assertEqual(self.client.get('/garage/compare').status_code, 302)
        self.assertEqual(self.post('add', self.slugs[3]).status_code, 302)
        self.assertEqual(self.store.list_slugs('GarageAlice'), self.slugs[:3])

    def test_next_redirect_cannot_leave_site(self):
        for destination in ('https://example.com', '//example.com', '/\\example.com', '/%5cexample.com', '/%2fexample.com', '/\n/example.com'):
            self.assertEqual(self.post('add', self.slugs[0], next=destination).location, '/garage')
        self.assertEqual(self.post('add', self.slugs[0], next='/collection?brand=ferrari').location, '/collection?brand=ferrari')

    def test_concurrent_saves_have_no_duplicates_or_rank_gaps(self):
        other_accounts = AccountStore(self.url)
        other = GarageStore(other_accounts)
        try:
            tasks = [(self.store if i % 2 else other, self.slugs[i % 3]) for i in range(12)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda task: task[0].add('GarageAlice', task[1]), tasks))
            with self.accounts.engine.connect() as connection:
                ranks = list(connection.scalars(select(favourites.c.rank).order_by(favourites.c.rank)))
            self.assertEqual(ranks, [1, 2, 3])
            self.assertEqual(set(self.store.list_slugs('GarageAlice')), set(self.slugs[:3]))
        finally:
            other_accounts.close()

    def test_missing_account_cannot_write(self):
        self.login('DeletedDriver')
        response = self.post('add', self.slugs[0])
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, '/login')
        self.assertEqual(self.store.list_slugs('DeletedDriver'), [])

    def test_storage_errors_have_generic_response(self):
        with patch.object(self.store, 'list_slugs', side_effect=StorageUnavailable('temporary failure')):
            response = self.client.get('/garage')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'postgresql://', response.data)

    def test_postgres_schema_has_account_foreign_key_and_composite_key(self):
        ddl = str(CreateTable(favourites).compile(dialect=postgresql.dialect()))
        self.assertIn('PRIMARY KEY (user_id, car_slug)', ddl)
        self.assertIn('REFERENCES users (id) ON DELETE CASCADE', ddl)
        self.assertIn('rank > 0', ddl)


if __name__ == '__main__':
    unittest.main()
