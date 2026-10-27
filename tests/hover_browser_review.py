"""Shared-menu behavior against a disposable local server (never production).

NAV12_TEST_URL=http://127.0.0.1:5002 python tests/hover_browser_review.py
Requires Playwright/Chromium; CHROMIUM_PATH may override the browser executable.
"""
import os
import time

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('NAV12_TEST_URL', 'http://127.0.0.1:5002').rstrip('/')


def menu_checks(browser):
    context = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    username = f'Hover{time.time_ns() % 10**12}'
    password = 'Disposable-hover-2026'
    page.goto(BASE + '/signup')
    page.locator('[name=username]').fill(username)
    page.locator('[name=password]').fill(password)
    page.locator('.account-form button[type=submit]').click()
    page.wait_for_url(BASE + '/login')
    page.locator('[name=username]').fill(username)
    page.locator('[name=password]').fill(password)
    page.locator('.account-form button[type=submit]').click()
    page.wait_for_url(BASE + '/dashboard')

    shell = page.locator('.nv-shared-menu')
    triggers = page.locator('.nv-explore-nav summary')
    heading = page.locator('.dashboard-heading')
    baseline = heading.bounding_box()['y']
    triggers.nth(0).hover()
    expect(triggers.nth(0)).to_have_attribute('aria-expanded', 'true')
    page.wait_for_timeout(350)
    assert heading.bounding_box()['y'] > baseline + 100, 'Menu must push content down'
    assert shell.evaluate('(el) => getComputedStyle(el).position') == 'relative'

    # Observe all animation frames through each switch: the surface never closes.
    for index in [1, 2, 3, 0]:
        page.evaluate("""() => {
          window.menuFrames = [];
          let end = performance.now() + 400;
          const sample = () => {
            const el = document.querySelector('.nv-shared-menu');
            window.menuFrames.push({open: el.classList.contains('is-open'),
                                    height: el.getBoundingClientRect().height});
            if (performance.now() < end) requestAnimationFrame(sample);
          };
          requestAnimationFrame(sample);
        }""")
        triggers.nth(index).hover()
        expect(triggers.nth(index)).to_have_attribute('aria-expanded', 'true')
        page.wait_for_timeout(450)
        frames = page.evaluate('window.menuFrames')
        assert frames and all(f['open'] and f['height'] > 10 for f in frames)
        assert page.locator('.nv-explore-panel.is-active').count() == 1

    # Nested brand previews still open and Escape closes one level at a time.
    page.locator('.nv-shared-menu .nv-brand-name').first.hover()
    preview = page.locator('.nv-shared-menu .nv-brand-preview').first
    expect(preview).to_be_visible()
    page.keyboard.press('Escape')
    expect(preview).to_be_hidden()
    expect(shell).to_have_class('nv-shared-menu is-open')
    page.keyboard.press('Escape')
    expect(triggers.nth(0)).to_be_focused()
    expect(triggers.nth(0)).to_have_attribute('aria-expanded', 'false')

    # Keyboard follows the logical trigger -> contents -> next trigger order.
    triggers.nth(1).focus()
    page.keyboard.press('Enter')
    page.keyboard.press('Tab')
    panel = page.locator('.nv-explore-panel.is-active')
    expect(panel.locator('a').first).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(triggers.nth(1)).to_be_focused()
    page.keyboard.press('ArrowDown')
    expect(panel.locator('a').first).to_be_focused()
    panel.locator('a').last.focus()
    page.keyboard.press('Tab')
    expect(triggers.nth(2)).to_be_focused()
    triggers.nth(3).hover()
    page.mouse.click(5, 5)
    expect(page.locator('[data-explore-menu][open]')).to_have_count(0)
    triggers.nth(4).hover()
    expect(triggers.nth(4)).to_have_attribute('aria-expanded', 'false')
    triggers.nth(4).click()
    expect(triggers.nth(4)).to_have_attribute('aria-expanded', 'true')
    search = page.locator('.nv-search-panel input[type=search]')
    expect(search).to_be_focused()
    search.fill('Ferrari')
    page.locator('.nv-search-panel button[type=submit]').click()
    page.wait_for_url('**/collection?q=Ferrari#catalogue')
    expect(page.locator('.nv-card')).to_have_count(1)
    assert not errors, errors

    state = context.storage_state()
    context.close()
    mobile = browser.new_context(viewport={'width': 390, 'height': 844},
                                 is_mobile=True, has_touch=True, storage_state=state,
                                 reduced_motion='reduce')
    page = mobile.new_page()
    page.goto(BASE + '/dashboard')
    triggers = page.locator('.nv-explore-nav summary')
    triggers.nth(1).tap()
    expect(triggers.nth(1)).to_have_attribute('aria-expanded', 'true')
    shell = page.locator('.nv-shared-menu')
    assert shell.evaluate('(el) => getComputedStyle(el).transitionDuration') == '0s'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    triggers.nth(1).tap()
    expect(triggers.nth(1)).to_have_attribute('aria-expanded', 'false')
    triggers.nth(4).tap()
    expect(triggers.nth(4)).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('.nv-search-panel input[type=search]')).to_be_focused()
    mobile.close()


if __name__ == '__main__':
    with sync_playwright() as playwright:
        options = {'args': ['--no-sandbox']}
        if os.environ.get('CHROMIUM_PATH'):
            options['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = playwright.chromium.launch(**options)
        try:
            menu_checks(browser)
            print('PASS: hover switches, layout flow, previews, keyboard, mobile, reduced motion')
        finally:
            browser.close()
