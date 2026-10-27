"""Horizontal exploration navigation QA against a disposable local Flask server.

Start the server with DATA_DIR set to disposable storage BEFORE importing app.
Then run: NAV12_TEST_URL=http://127.0.0.1:5002 python tests/navigation_browser_review.py
Requires Playwright and a Chromium executable (CHROMIUM_PATH can override it).
Only synthetic credentials are submitted; no workbook is opened by this script.
"""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get('NAV12_TEST_URL', 'http://127.0.0.1:5002').rstrip('/')
OUT = Path(os.environ.get('NAV12_QA_OUTPUT', 'work/navigation-review'))
OUT.mkdir(parents=True, exist_ok=True)
LABELS = ['Car Brands', 'Engine Types', 'Driving Character', 'Powertrains']
report = {'checks': [], 'screenshots': [], 'errors': [], 'failed_requests': []}


def passed(label):
    report['checks'].append(label)


def watch(page):
    page.on('pageerror', lambda error: report['errors'].append(str(error)))
    page.on('console', lambda message: report['errors'].append(message.text)
            if message.type == 'error' else None)
    page.on('requestfailed', lambda request: report['failed_requests'].append(request.url))


def menu(page, label):
    return page.locator('.nv-explore-nav [data-explore-menu]').filter(
        has=page.locator('summary', has_text=label))


def panel(item):
    hooked = item.locator('[data-explore-panel]')
    return hooked.first if hooked.count() else item.locator(':scope > :not(summary)').first


def no_overflow(page, label):
    sizes = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
    if sizes['scroll'] > sizes['width'] + 1:
        overflowing = page.evaluate("""() => [...document.querySelectorAll('body *')]
            .filter(el => { const box = el.getBoundingClientRect();
                return box.width && (box.left < -1 || box.right > innerWidth + 1)
                    && !el.closest('.nv-nav-track'); })
            .slice(0, 12).map(el => ({tag: el.tagName, class: el.className,
                left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right}))""")
        raise AssertionError((label, sizes, overflowing))


def check_menu_bounds(page, item, label):
    box = panel(item).bounding_box()
    width, height = page.evaluate('[innerWidth, innerHeight]')
    assert box and box['x'] >= -1 and box['x'] + box['width'] <= width + 1, (label, box, width)
    assert box['y'] >= -1 and box['y'] + box['height'] <= height + 1, (label, box, height)


def screenshot(page, name, full=False):
    page.evaluate("document.querySelectorAll('img[loading=lazy]').forEach(i=>i.loading='eager')")
    page.evaluate("async () => Promise.all([...document.images].map(i=>i.decode().catch(()=>{})))")
    page.wait_for_timeout(250)
    page.screenshot(path=str(OUT / f'{name}.png'), full_page=full)
    report['screenshots'].append(f'{name}.png')


def check_nav_row(page, label):
    nav = page.locator('.nv-explore-nav')
    assert nav.count() == 1, label
    summaries = nav.locator('[data-explore-menu] > summary')
    assert summaries.count() == 4, label
    for index, expected in enumerate(LABELS):
        assert expected in summaries.nth(index).inner_text(), (label, index)
    boxes = summaries.evaluate_all('(items)=>items.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,h:r.height}})')
    assert max(box['y'] for box in boxes) - min(box['y'] for box in boxes) <= 2, (label, boxes)
    assert all(boxes[index]['x'] < boxes[index + 1]['x'] for index in range(3)), (label, boxes)
    no_overflow(page, label)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
        args=['--no-sandbox'])
    report['browser'] = browser.version
    report['environment'] = 'Linux headless Chromium; viewport/touch emulation, no physical device'
    context = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = context.new_page()
    watch(page)
    try:
        username = f'NavReview{time.time_ns() % 10**12}'
        password = 'Disposable-navigation-2026'
        page.goto(BASE + '/signup')
        page.locator('[name=username]').fill(username)
        page.locator('[name=password]').fill(password)
        page.locator('.account-form button[type=submit]').click()
        page.wait_for_url(BASE + '/login')
        page.locator('[name=username]').fill(username)
        page.locator('[name=password]').fill(password)
        page.locator('.account-form button[type=submit]').click()
        page.wait_for_url(BASE + '/dashboard')
        assert page.locator('svg.v12-pro').count() == 1
        check_nav_row(page, 'dashboard')
        screenshot(page, 'navigation-dashboard-desktop', True)
        passed('Synthetic signup/login and preserved dashboard with four sections in one row')

        for label in LABELS:
            item = menu(page, label)
            item.locator('summary').click()
            assert item.evaluate('(el)=>el.open'), label
            assert page.locator('[data-explore-menu][open]').count() == 1
            check_menu_bounds(page, item, label)
        page.locator('h1').first.click()
        assert page.locator('[data-explore-menu][open]').count() == 0
        passed('Click switches a single open menu; outside click closes it')

        for label in LABELS:
            item = menu(page, label)
            summary = item.locator('summary')
            summary.focus()
            page.keyboard.press('Enter')
            assert item.evaluate('(el)=>el.open'), label
            page.keyboard.press('Tab')
            assert item.evaluate('(el)=>el.contains(document.activeElement)'), label
            page.keyboard.press('Escape')
            # Brands may first close a focused preview, then its parent menu.
            if item.evaluate('(el)=>el.open'):
                page.keyboard.press('Escape')
            assert not item.evaluate('(el)=>el.open'), label
            assert summary.evaluate('(el)=>el===document.activeElement'), label
        passed('Native keyboard opening, links reachable by Tab, Escape returns focus to summary')

        item = menu(page, 'Car Brands')
        item.locator('summary').click()
        item.locator('[data-brand-link]').filter(has_text='Lamborghini').hover()
        visible_preview = item.locator('.nv-brand-preview:visible')
        visible_preview.wait_for()
        assert visible_preview.count() == 1
        visible_preview.locator('.nv-preview-model').hover()
        page.wait_for_timeout(250)
        assert visible_preview.is_visible()
        menu(page, 'Engine Types').locator('summary').click()
        assert not item.evaluate('(el)=>el.open')
        assert page.locator('.nv-brand-preview:visible').count() == 0
        screenshot(page, 'navigation-engine-menu-desktop')
        passed('Existing brand hover preview survives pointer travel and closes when switching sections')

        engines = menu(page, 'Engine Types')
        engines.locator('a[href="/engines/na-v12"]').click()
        page.wait_for_url(BASE + '/engines/na-v12')
        assert page.locator('.nv-card').count() == 2
        screenshot(page, 'navigation-na-v12-guide', True)
        page.goto(BASE + '/engines/v6')
        assert page.locator('.nv-card').count() == 0
        assert page.locator('.nv-empty').is_visible()
        page.goto(BASE + '/engines/twin-turbo-v12')
        assert page.locator('.nv-card').count() == 0
        assert page.locator('.nv-empty').is_visible()
        page.goto(BASE + '/engines')
        check_nav_row(page, 'engine guide')
        screenshot(page, 'navigation-engine-guide-desktop', True)
        passed('Engine links lead to real guide pages, exact NA V12 cars, and honest zero-car V6/turbo V12 guides')

        menu(page, 'Driving Character').locator('summary').click()
        menu(page, 'Driving Character').locator('.nv-topic-link').filter(has_text='Grand tourer').click()
        assert page.locator('#character-filter').input_value() == 'Grand tourer'
        assert page.locator('.nv-card').count() == 4
        menu(page, 'Powertrains').locator('summary').click()
        menu(page, 'Powertrains').locator('.nv-topic-link').filter(has_text='Plug-in hybrid').click()
        assert page.locator('#powertrain-filter').input_value() == 'Plug-in hybrid'
        assert page.locator('.nv-card').count() == 1
        passed('Driving Character and Powertrains menu links apply real filters with accurate results')

        page.goto(BASE + '/collection')
        page.locator('#engine-filter').select_option('v8')
        page.locator('.nv-filter-submit').click()
        assert page.locator('.nv-card').count() == 3
        assert 'engine=v8' in page.url
        page.reload()
        assert page.locator('#engine-filter').input_value() == 'v8'
        page.locator('#character-filter').select_option('Grand tourer')
        page.locator('.nv-filter-submit').click()
        assert page.locator('.nv-card').count() == 2
        screenshot(page, 'navigation-engine-filter-desktop', True)
        page.locator('#brand-filter').select_option('porsche')
        page.locator('.nv-filter-submit').click()
        assert page.locator('.nv-empty').is_visible()
        page.get_by_role('link', name='Reset filters').click()
        assert page.locator('.nv-card').count() == 10
        assert page.locator('#engine-filter').input_value() == ''
        passed('Engine filter composes with character/brand, persists on reload, handles zero, and resets')

        page.goto(BASE + '/collection')
        menu(page, 'Engine Types').locator('summary').click()
        screenshot(page, 'navigation-collection-engine-menu')
        menu(page, 'Car Brands').locator('summary').click()
        menu(page, 'Car Brands').locator('[data-brand-link]').filter(has_text='Lamborghini').hover()
        menu(page, 'Car Brands').locator('.nv-brand-preview:visible').wait_for()
        screenshot(page, 'navigation-collection-brands-menu')

        for width in [360, 390, 768, 1280, 1920]:
            page.set_viewport_size({'width': width, 'height': 900 if width >= 768 else 844})
            for route in ['/dashboard', '/collection', '/engines', '/engines/na-v12',
                          '/brands/lamborghini', '/cars/lamborghini-revuelto']:
                page.goto(BASE + route)
                check_nav_row(page, f'{width}px {route}')
            page.goto(BASE + '/collection')
            for label in LABELS:
                item = menu(page, label)
                item.locator('summary').click()
                check_menu_bounds(page, item, f'{width}px {label}')
                no_overflow(page, f'{width}px open {label}')
            page.keyboard.press('Escape')
            page.locator('h1').first.click()
            page.locator('.nv-nav-track').evaluate('(el)=>el.scrollLeft=0')
            screenshot(page, f'navigation-collection-{width}')
            passed(f'{width}px: one nav row and no page overflow across six routes; all menus fit viewport')

        state = context.storage_state()
        mobile_context = browser.new_context(viewport={'width': 390, 'height': 844},
            is_mobile=True, has_touch=True, device_scale_factor=1, storage_state=state)
        touch = mobile_context.new_page()
        watch(touch)
        touch.goto(BASE + '/collection')
        screenshot(touch, 'navigation-mobile-default')
        touch.goto(BASE + '/dashboard')
        track = touch.locator('.nv-nav-track')
        assert track.evaluate('(el)=>el.scrollWidth > el.clientWidth')
        track.evaluate('(el)=>el.scrollLeft=el.scrollWidth')
        assert track.evaluate('(el)=>el.scrollLeft > 0')
        power = menu(touch, 'Powertrains')
        power.locator('summary').tap()
        assert power.evaluate('(el)=>el.open')
        check_menu_bounds(touch, power, 'mobile touch powertrains')
        screenshot(touch, 'navigation-mobile-powertrain-menu')
        touch.locator('h1').first.tap()
        assert touch.locator('[data-explore-menu][open]').count() == 0
        menu(touch, 'Engine Types').locator('summary').tap()
        engine_menu = menu(touch, 'Engine Types')
        check_menu_bounds(touch, engine_menu, 'mobile engine menu')
        screenshot(touch, 'navigation-mobile-engine-menu')
        engine_menu.locator('a[href="/engines/flat-six"]').tap()
        touch.wait_for_url(BASE + '/engines/flat-six')
        assert touch.locator('.nv-card').count() == 1
        screenshot(touch, 'navigation-mobile-flat-six-guide', True)
        passed('Touch emulation: horizontally scrollable nav, clamped menus, outside dismissal and real engine navigation')

        plain_context = browser.new_context(java_script_enabled=False,
            viewport={'width': 390, 'height': 844}, storage_state=state)
        plain = plain_context.new_page()
        watch(plain)
        plain.goto(BASE + '/dashboard')
        check_nav_row(plain, 'no JavaScript dashboard')
        menu(plain, 'Engine Types').locator('summary').click()
        menu(plain, 'Engine Types').locator('a[href="/engines/v8"]').click()
        plain.wait_for_url(BASE + '/engines/v8')
        assert plain.locator('.nv-card').count() == 3
        plain.goto(BASE + '/collection')
        plain.locator('#engine-filter').select_option('flat-six')
        plain.locator('.nv-filter-submit').click()
        assert plain.locator('.nv-card').count() == 1
        plain.locator('.nv-card-link').click()
        plain.wait_for_url(BASE + '/cars/porsche-911-gt3')
        passed('JavaScript disabled: native menus, engine guide links, GET filter and car navigation work')

        assert not report['errors'], report['errors']
        assert not report['failed_requests'], report['failed_requests']
        (OUT / 'failure.png').unlink(missing_ok=True)
    except Exception as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        page.screenshot(path=str(OUT / 'failure.png'), full_page=True)
        raise
    finally:
        browser.close()
        (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')

print(json.dumps(report, indent=2))
