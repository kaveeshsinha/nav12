"""Garage regression checks against a disposable in-memory database and local server.

Run: python tests/garage_browser_review.py
Requires Playwright and Chromium. Optional environment variables:
CHROMIUM_PATH overrides the browser executable; NAV12_SCREENSHOT_DIR saves previews.
"""
import logging
import os
from pathlib import Path
import sys
import threading

from playwright.sync_api import expect, sync_playwright


def run():
    # Never connect this test to a configured development or production database.
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['APP_ENV'] = 'development'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import app
    from werkzeug.serving import make_server

    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    output = os.environ.get('NAV12_SCREENSHOT_DIR')

    def screenshot(page, name):
        if output:
            folder = Path(output)
            folder.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(folder / name), full_page=True)

    try:
        with sync_playwright() as p:
            options = {'headless': True, 'args': ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']}
            if os.environ.get('CHROMIUM_PATH'):
                options['executable_path'] = os.environ['CHROMIUM_PATH']
            browser = p.chromium.launch(**options)
            page = browser.new_page(viewport={'width': 1440, 'height': 1050})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/signup')
            page.locator('[name=username]').fill('GarageBrowserQA')
            page.locator('[name=password]').fill('Disposable-garage-2026')
            page.locator('.account-form button[type=submit]').click()
            page.wait_for_url(base + '/login')
            page.locator('[name=username]').fill('GarageBrowserQA')
            page.locator('[name=password]').fill('Disposable-garage-2026')
            expect(page.locator('.headlight-toggle')).to_be_visible()
            page.locator('.headlight-toggle').click()
            expect(page.locator('#password')).to_have_attribute('type', 'text')
            page.locator('.account-form button[type=submit]').click()
            page.wait_for_url(base + '/dashboard')
            page.goto(base + '/garage')
            expect(page.locator('#empty-garage-title')).to_be_visible()
            for slug in ['ferrari-812-superfast', 'lamborghini-revuelto', 'porsche-911-gt3']:
                page.goto(base + '/cars/' + slug)
                page.locator('#gallery-content > .nv-favourite-form .nv-favourite-button').click()
                expect(page.locator('#gallery-content > .nv-favourite-form .nv-favourite-button')).to_contain_text('Saved to favourites')
            page.goto(base + '/collection?brand=bmw')
            page.locator('.nv-favourite-button').first.click()
            assert 'brand=bmw' in page.url
            expect(page.locator('.nv-favourite-button').first).to_contain_text('Saved to favourites')
            page.locator('.nv-favourite-button').first.click()
            assert 'brand=bmw' in page.url
            expect(page.locator('.nv-favourite-button').first).to_contain_text('Save to favourites')
            page.goto(base + '/garage')
            expect(page.locator('.nv-garage-card')).to_have_count(3)
            # A full-page capture alone does not reliably load lazy pictures.
            page.locator('.nv-garage-card img').evaluate_all("images => images.forEach(image => image.loading = 'eager')")
            assert page.locator('.nv-garage-card img').first.evaluate(
                'image => image.decode().then(() => image.naturalWidth > 0)')
            for card in page.locator('.nv-garage-card').all():
                link = card.locator('.nv-garage-car-link').bounding_box()
                actions = card.locator('.nv-garage-card-actions').bounding_box()
                assert link['y'] + link['height'] <= actions['y'] + 1, 'Ranking controls must not overlap car details'
            screenshot(page, 'garage-desktop.png')
            expect(page.locator('#garage-compare button[type=submit]')).to_be_disabled()
            page.locator('[data-compare-car]').nth(0).check()
            expect(page.locator('#garage-compare button[type=submit]')).to_be_disabled()
            page.locator('[data-compare-car]').nth(1).check()
            expect(page.locator('#garage-compare button[type=submit]')).to_be_enabled()
            page.locator('#garage-compare button[type=submit]').click()
            expect(page.locator('.nv-garage-table thead th')).to_have_count(3)
            screenshot(page, 'garage-compare.png')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Comparison must scroll inside its region, not the page'
            screenshot(page, 'garage-compare-mobile.png')
            page.goto(base + '/garage')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('.nv-garage-rank-form select').nth(2).select_option('1')
            page.locator('.nv-garage-rank-form button').nth(2).click()
            expect(page.locator('.nv-garage-card h2').first).to_contain_text('911 GT3')
            screenshot(page, 'garage-mobile.png')
            page.locator('.nv-garage-remove-form button').first.click()
            expect(page.locator('.nv-garage-card')).to_have_count(2)
            assert not errors, errors
            browser.close()
            print('Garage browser checks passed: add, remove, rank, compare, filter preservation, desktop/mobile layout and JavaScript errors.')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        app.extensions['accounts'].close()


if __name__ == '__main__':
    run()
