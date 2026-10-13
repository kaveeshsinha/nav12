"""Run: python -m unittest discover -s tests -v. Never opens the real workbook."""
import os
import re
import json
import tempfile
import unittest
from pathlib import Path

_storage = tempfile.TemporaryDirectory(prefix='nav12-test-')
os.environ['DATA_DIR'] = _storage.name  # Set BEFORE app import (startup opens Excel).
os.environ['APP_ENV'] = 'development'
from app import app, rate_buckets, account
from collection import CARS, BRANDS, ASSETS


class NaV12Tests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, USER_FILE=Path(_storage.name) / 'users.xlsx')
        rate_buckets.clear()
        self.client = app.test_client()

    def token(self, route='/login'):
        response = self.client.get(route)
        return re.search(rb'name="csrf_token" value="([^"]+)"', response.data)[1].decode()

    def member(self):
        with self.client.session_transaction() as session:
            session['username'] = 'TestDriver'

    def test_account_lifecycle_hash_duplicate_and_session(self):
        name='LifecycleDriver'
        response=self.client.post('/signup', data={'csrf_token':self.token('/signup'), 'username':name, 'password':'Test-password-2026'})
        self.assertEqual(response.status_code,302)
        saved=account(name)
        self.assertNotEqual(saved,'Test-password-2026')
        self.assertTrue(saved.startswith(('scrypt:', 'pbkdf2:')))
        duplicate=self.client.post('/signup',data={'csrf_token':self.token('/signup'),'username':name.lower(),'password':'Other-password-2026'})
        self.assertIn(b'Username already exists',duplicate.data)
        self.assertEqual(account(name),saved)
        bad=self.client.post('/login',data={'csrf_token':self.token(),'username':name,'password':'wrong'})
        self.assertIn(b'Incorrect credentials',bad.data)
        response=self.client.post('/login',data={'csrf_token':self.token(),'username':name,'password':'Test-password-2026'})
        self.assertEqual(response.location,'/dashboard')
        self.assertEqual(self.client.get('/collection').status_code,200)
        token=self.token('/dashboard')
        self.assertEqual(self.client.post('/logout',data={'csrf_token':token}).status_code,302)
        self.assertEqual(self.client.get('/dashboard').status_code,302)

    def test_all_forms_reject_missing_wrong_and_stale_csrf(self):
        for path in ('/signup','/login','/logout'):
            for token in ('','wrong'):
                self.assertEqual(self.client.post(path,data={'csrf_token':token}).status_code,400)
        token=self.token()
        self.client.post('/logout',data={'csrf_token':token})
        self.assertEqual(self.client.post('/login',data={'csrf_token':token}).status_code,400)
        self.assertEqual(self.client.get('/logout').status_code,405)

    def test_auth_validation_and_rate_limit_preserved(self):
        token=self.token('/signup')
        response=self.client.post('/signup',data={'csrf_token':token,'username':'=formula','password':'short'})
        self.assertIn(b'Use 3',response.data)
        for i in range(10):
            self.assertEqual(self.client.post('/login',data={'csrf_token':token,'username':'NoSuchDriver','password':'x'}).status_code,200)
        limited=self.client.post('/login',data={'csrf_token':token,'username':'NoSuchDriver','password':'x'})
        self.assertEqual(limited.status_code,429)
        self.assertEqual(limited.headers['Retry-After'],'60')

    def test_member_routes_protected(self):
        for route in ['/dashboard','/collection','/collection/credits']+[f'/brands/{slug}' for slug in BRANDS]+[f'/cars/{slug}' for slug in CARS]:
            self.assertEqual(self.client.get(route).status_code,302,route)

    def test_every_catalogue_route_renders(self):
        self.member()
        for route in ['/dashboard','/collection','/collection/credits']+[f'/brands/{slug}' for slug in BRANDS]+[f'/cars/{slug}' for slug in CARS]:
            self.assertEqual(self.client.get(route).status_code,200,route)

    def test_invalid_routes_return_404_with_recovery(self):
        self.member()
        for route in ('/brands/not-a-brand','/cars/not-a-car'):
            response=self.client.get(route)
            self.assertEqual(response.status_code,404)
            self.assertIn(b'Explore the collection',response.data)

    def test_dashboard_svg_preserved_and_collection_link_works(self):
        self.member()
        response=self.client.get('/dashboard')
        self.assertIn(b'class="v12-pro"',response.data)
        self.assertIn(b'url(#metalTop)',response.data)
        self.assertIn(b'href="/collection"',response.data)
        self.assertIn(b'800 PS',response.data)

    def test_search_filters_counts_and_empty_state(self):
        self.member()
        cases=[('/collection',10),('/collection?q=812',1),('/collection?brand=porsche',1),('/collection?powertrain=Plug-in+hybrid',1),('/collection?character=Grand+tourer',4),('/collection?brand=ferrari&q=911',0),('/collection?brand=unknown',0)]
        for route,count in cases:
            response=self.client.get(route)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.data.count(b'<article class="nv-card">'),count,route)
            self.assertIn(f'{count} of 10 cars'.encode(),response.data)
            if count==0:self.assertIn(b'No cars match',response.data)
        self.assertIn(b'value="812"',self.client.get('/collection?q=812').data)
        self.assertNotIn(b'<script>alert(1)',self.client.get('/collection?q=%3Cscript%3Ealert(1)').data)

    def test_csp_only_expanded_for_gallery_pages(self):
        for path in ('/login','/signup','/healthz'):
            self.assertIn("script-src 'none'",self.client.get(path).headers['Content-Security-Policy'])
        self.member()
        response=self.client.get('/collection')
        csp=response.headers['Content-Security-Policy']
        self.assertIn("script-src 'self'",csp)
        self.assertNotIn('unsafe-eval',csp)
        for policy in ("img-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "form-action 'self'"):
            self.assertIn(policy,csp)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        cookies=self.client.get('/login').headers.getlist('Set-Cookie')
        self.assertTrue(app.config['SESSION_COOKIE_HTTPONLY'])
        self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'],'Lax')

    def test_media_files_catalogue_and_sources_integrity(self):
        self.assertEqual(len(BRANDS),10)
        for car in CARS.values():
            self.assertIn(car['brand'],BRANDS)
            self.assertTrue(car['source'].startswith('https://'))
            self.assertIsInstance(car['year'],int)
            for key in car['images']:
                self.assertIn(key,ASSETS)
        for key,asset in ASSETS.items():
            self.assertTrue(asset['license'])
            for suffix in ('-480.webp','-960.webp','-1600.webp','-1600.jpg'):
                self.assertTrue((Path(app.static_folder)/(asset['file']+suffix)).is_file(),key+suffix)

    def test_account_files_never_exposed(self):
        for path in ('/data/users.xlsx','/catalogue/users.xlsx','/static/../data/users.xlsx'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertTrue(str(app.config['USER_FILE']).startswith(_storage.name))


if __name__=='__main__': unittest.main()
