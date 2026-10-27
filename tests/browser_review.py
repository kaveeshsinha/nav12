"""Browser QA for a locally running, disposable-data instance.
Usage: NAV12_TEST_URL=http://127.0.0.1:5002 python tests/browser_review.py
The server MUST be launched with DATA_DIR pointing to disposable test storage.
"""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE=os.environ.get('NAV12_TEST_URL','http://127.0.0.1:5002')
OUT=Path(os.environ.get('NAV12_QA_OUTPUT','work/browser-review'))
OUT.mkdir(parents=True,exist_ok=True)
report={'checks':[], 'screenshots':[], 'errors':[], 'failed_requests':[], 'engine_limits':[]}
def passed(name): report['checks'].append(name)
def no_overflow(page,label):
    sizes=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
    assert sizes['scroll']<=sizes['width']+1,(label,sizes)

def screenshot(page,name,full=True):
    # Resolve lazy media throughout page before full-page screenshot.
    page.evaluate("document.querySelectorAll('img[loading=lazy]').forEach(i=>i.loading='eager')")
    page.evaluate("async () => { await Promise.all(Array.from(document.querySelectorAll('.nv-photo img')).map(i=>i.decode().catch(()=>{}))); }")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT/(name+'.png')),full_page=full)
    report['screenshots'].append(name+'.png')

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
    report['browser']=browser.version
    report['environment']='Linux headless Chromium on cloud host; no physical mobile device'
    context=browser.new_context(viewport={'width':1280,'height':900})
    page=context.new_page()
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    page.on('console',lambda message:report['errors'].append(message.text) if message.type=='error' else None)
    page.on('requestfailed',lambda request:report['failed_requests'].append(request.url))
    username=f'Review{int(time.time())}'
    page.goto(BASE+'/signup');page.locator('[name=username]').fill(username);page.locator('[name=password]').fill('Disposable-review-2026');page.locator('.account-form button[type=submit]').click()
    page.locator('[name=username]').fill(username);page.locator('[name=password]').fill('Disposable-review-2026');page.locator('.account-form button[type=submit]').click()
    assert page.url.endswith('/dashboard');assert page.locator('svg.v12-pro').count()==1
    passed('Browser signup, login, dashboard and preserved inline V12 SVG')
    screenshot(page,'after-dashboard')
    page.get_by_role('link',name='Explore the collection').click()
    assert page.url.endswith('/collection');assert page.locator('.nv-card').count()==10
    screenshot(page,'collection-desktop');screenshot(page,'collection-desktop-viewport',False)
    report['navigation_timing']=page.evaluate("({duration:performance.getEntriesByType('navigation')[0].duration,domContentLoaded:performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd,resourceBytes:performance.getEntriesByType('resource').reduce((sum,r)=>sum+r.transferSize,0)})")
    # Hover delay, movement into panel, single preview, model navigation and Back.
    page.locator('.nv-brands summary').click()
    name=page.locator('.nv-brands [data-brand-link]').nth(1)
    name.hover();panel=page.locator('#nav-brands-lamborghini');panel.wait_for(state='visible');page.wait_for_timeout(350)
    panel.locator('.nv-preview-model').hover();page.wait_for_timeout(250)
    assert panel.is_visible();assert page.locator('.nv-brand-preview:visible').count()==1
    screenshot(page,'brand-preview-desktop',False)
    panel.locator('.nv-preview-model').click();assert page.url.endswith('/cars/lamborghini-revuelto')
    page.go_back();assert page.url.endswith('/collection')
    passed('Hover preview, pointer travel, single-panel visibility, direct model link and Back')
    # Keyboard focus and dismissal.
    page.locator('.nv-brands summary').click() if not page.locator('.nv-brands').get_attribute('open') else None
    # Use evaluate to inspect boolean attribute; empty string is valid open.
    page.locator('.nv-brands').evaluate('(el)=>el.open=true')
    name=page.locator('.nv-brands [data-brand-link]').nth(2);name.focus()
    panel=page.locator('#nav-brands-porsche');assert panel.is_visible()
    page.keyboard.press('Tab');assert page.locator('.nv-brands [aria-label="Preview Porsche"]').evaluate('(el)=>el===document.activeElement')
    page.keyboard.press('Tab');assert panel.locator('.nv-preview-close').evaluate('(el)=>el===document.activeElement')
    page.keyboard.press('Tab');assert panel.locator('.nv-preview-model').evaluate('(el)=>el===document.activeElement')
    page.keyboard.press('Escape');assert not panel.is_visible();assert page.locator('.nv-brands [aria-label="Preview Porsche"]').get_attribute('aria-expanded')=='false'
    page.keyboard.press('Tab');assert page.locator('.nv-brands [data-brand-link]').nth(3).evaluate('(el)=>el===document.activeElement')
    page.keyboard.press('Escape');page.keyboard.press('Escape')
    passed('Keyboard preview, logical Tab order, Escape return focus, no focus trap')
    # Rapid hover switches never leave stacked/stuck panels.
    page.locator('.nv-brands').evaluate('(el)=>el.open=true')
    for index in [0,2,1,7,4,0,1]:page.locator('.nv-brands [data-brand-link]').nth(index).hover()
    page.wait_for_timeout(450)
    assert page.locator('.nv-brand-preview:visible').count()==1
    page.locator('h1').hover();page.wait_for_timeout(300);assert page.locator('.nv-brand-preview:visible').count()==0
    page.locator('.nv-brands summary').click()
    passed('Rapid hover switching and pointer dismissal')
    page.locator('.nv-directory [data-brand-link]').nth(1).focus();page.wait_for_timeout(300)
    assert page.locator('#directory-lamborghini').is_visible()
    page.keyboard.press('Escape')
    passed('Directory keyboard focus survives automatic scrolling')
    page.locator('#search-cars').fill('812');page.locator('.nv-filter-submit').click();assert page.locator('.nv-card').count()==1;assert 'q=812' in page.url
    page.reload();assert page.locator('#search-cars').input_value()=='812'
    page.locator('#brand-filter').select_option('porsche');page.locator('.nv-filter-submit').click();assert page.locator('.nv-empty').is_visible()
    page.get_by_role('link',name='Reset filters').click();assert page.locator('.nv-card').count()==10
    page.locator('#powertrain-filter').select_option('Plug-in hybrid');page.locator('.nv-filter-submit').click();assert page.locator('.nv-card').count()==1
    passed('Search, combined filters, URL reload state, accurate counts, empty state and reset')
    page.goto(BASE+'/brands/lamborghini');screenshot(page,'brand-desktop')
    page.goto(BASE+'/cars/lamborghini-revuelto');screenshot(page,'model-desktop')
    page.locator('[data-gallery-image]').nth(0).click();assert page.locator('dialog').is_visible()
    page.get_by_role('button',name='Next photograph',exact=True).click();assert page.locator('[data-gallery-counter]').inner_text()=='2 / 4'
    page.keyboard.press('ArrowLeft');assert page.locator('[data-gallery-counter]').inner_text()=='1 / 4'
    page.keyboard.press('Escape');assert not page.locator('dialog').is_visible()
    assert page.locator('[data-gallery-image]').nth(0).evaluate('(el)=>el===document.activeElement')
    passed('Gallery dialog, next/previous, arrow keys, Escape, focus restoration')
    for width in [360,390,768,1280,1920]:
        page.set_viewport_size({'width':width,'height':900 if width>=768 else 844})
        for route in ['/collection','/brands/lamborghini','/cars/lamborghini-revuelto','/cars/bentley-continental-gt-speed']:
            page.goto(BASE+route);no_overflow(page,f'{width}: {route}')
        passed(f'No horizontal overflow: {width}px collection, brand, model, long model title')
        if width in [360,390,768,1920]:
            page.goto(BASE+'/collection');screenshot(page,f'collection-{width}')
        if width==390:
            screenshot(page,'collection-mobile-viewport',False)
            page.goto(BASE+'/brands/lamborghini');screenshot(page,'brand-mobile')
            page.goto(BASE+'/cars/lamborghini-revuelto');screenshot(page,'model-mobile')
    page.set_viewport_size({'width':1280,'height':900});page.goto(BASE+'/collection')
    page.evaluate("document.documentElement.style.zoom='2'");page.wait_for_timeout(200);no_overflow(page,'200% CSS zoom');screenshot(page,'collection-zoom200',False)
    passed('200% CSS layout zoom (browser UI zoom not automated)')
    page.evaluate("document.documentElement.style.zoom='1'")
    state=context.storage_state()
    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1,storage_state=state)
    touch=mobile.new_page();touch.goto(BASE+'/collection');touch.locator('.nv-brands summary').tap();toggle=touch.locator('.nv-brands [aria-label="Preview Lamborghini"]');toggle.tap();assert toggle.get_attribute('aria-expanded')=='true';preview=touch.locator('#nav-brands-lamborghini');bounds=preview.bounding_box();assert bounds['x']>=0 and bounds['x']+bounds['width']<=390
    screenshot(touch,'brand-preview-mobile',False)
    preview.locator('.nv-preview-close').tap();assert toggle.get_attribute('aria-expanded')=='false'
    touch.locator('.nv-brands [data-brand-link]').nth(1).tap();touch.wait_for_url(BASE+'/brands/lamborghini');assert touch.url.endswith('/brands/lamborghini')
    passed('Touch: separate labelled preview toggle, close, viewport fit, brand first-tap navigation')
    reduced=browser.new_context(viewport={'width':1280,'height':900},reduced_motion='reduce',storage_state=state)
    reduced_page=reduced.new_page();reduced_page.goto(BASE+'/collection');reduced_page.locator('.nv-brands').evaluate('(el)=>el.open=true');reduced_page.locator('.nv-brands [data-brand-link]').nth(1).focus()
    assert reduced_page.locator('#nav-brands-lamborghini').evaluate("el=>getComputedStyle(el).animationName")=='none'
    assert reduced_page.locator('.nv-feature img').evaluate("el=>getComputedStyle(el).transitionDuration")=='0s'
    passed('Reduced motion removes animations/transitions and retains previews')
    nojs=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844},storage_state=state)
    plain=nojs.new_page();plain.goto(BASE+'/collection');plain.locator('#search-cars').fill('911');plain.locator('.nv-filter-submit').click();assert plain.locator('.nv-card').count()==1;plain.locator('.nv-card-link').click();assert plain.url.endswith('/cars/porsche-911-gt3');assert plain.locator('#specifications').count()==1
    plain.locator('[data-gallery-image]').first.click();assert plain.url.endswith('.jpg');plain.go_back()
    passed('JavaScript disabled: GET search, car navigation, specs, gallery image link, Back')
    # Separate context for intentional image failures so main-console report stays meaningful.
    failure=browser.new_context(storage_state=state);broken=failure.new_page();broken.route('**/static/collection/media/**',lambda route:route.abort());broken.goto(BASE+'/collection');broken.wait_for_timeout(500);assert broken.locator('.nv-feature .nv-photo-error').is_visible()
    passed('Image failure presents readable model-specific fallback')
    # Local Chromium throttling only; no device FPS claim.
    cdp=context.new_cdp_session(page);cdp.send('Emulation.setCPUThrottlingRate',{'rate':4});page.goto(BASE+'/collection');page.locator('.nv-brands').evaluate('(el)=>el.open=true');start=time.perf_counter();page.locator('.nv-brands [data-brand-link]').nth(1).hover();page.locator('#nav-brands-lamborghini').wait_for(state='visible');report['preview_4x_cpu_ms']=round((time.perf_counter()-start)*1000,1);cdp.send('Emulation.setCPUThrottlingRate',{'rate':1})
    passed('Preview responds under 4x CPU throttle; measured host timing recorded')
    page.goto(BASE+'/dashboard');page.locator('form[action="/logout"] button').click();page.goto(BASE+'/collection');assert page.url.endswith('/login')
    passed('Browser logout clears collection access')
    for name in ('firefox','webkit'):
        try:
            other=getattr(p,name).launch();other.close();report['engine_limits'].append(name+' available but not suite-tested')
        except Exception as error:report['engine_limits'].append(name+': unavailable ('+str(error).splitlines()[0]+')')
    browser.close()
(OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
assert not report['errors'],report['errors']
assert not report['failed_requests'],report['failed_requests']
print(json.dumps(report,indent=2))
