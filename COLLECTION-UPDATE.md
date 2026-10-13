> This describes the first collection release. For the latest navigation and engine-guide changes, setup and verification, see [NAVIGATION-UPDATE.md](NAVIGATION-UPDATE.md).

# NaV12 · Car Collection update

Local review edition, 13 October 2026. Nothing was pushed, merged, deployed or purchased.

## Baseline and scope

The supplied `/workspace/nav12` checkout was clean on branch `work`, commit `8f45c86a90697f1fd56d4c735e335519d70d849a`. `git ls-remote` confirmed that GitHub `main` and remote HEAD pointed to the same commit. Development took place in a separate local clone on `feature/automotive-gallery`. The original checkout and its account data were not modified.

The real entry point is `app.py`; `Procfile` and `wsgi_pythonanywhere.py` use `app:app` / `from app import app as application` as documented in their unchanged files. Authentication uses Flask sessions, Werkzeug password hashes, custom CSRF validation, and locked OpenPyXL storage. `DATA_DIR` still selects the existing workbook location; its default remains `data/users.xlsx` beside `app.py`. Startup opens that workbook, so set `DATA_DIR` **before importing or starting the application** during review.

There was no installed Car Collection implementation or uploaded earlier ZIP. The dashboard had ten placeholder brand links, three editorial shortlist cards, and an original inline SVG V12 illustration. There is **no interactive 3D viewer, GLB asset, model-viewer script or engine control in this baseline**. The SVG is preserved byte for byte. No real account rows were read or copied.

## What changed

- `/collection`: photography-led feature, the original **Car Brands** entry point, brand discovery, ten model records, search and brand/powertrain/character filters. GET parameters preserve state; counts, reset and empty results work without JavaScript.
- `/brands/<slug>`: shared editorial structure, brand introduction, featured model and model grid. All ten original brands are retained. One curated model per brand; no inflated placeholder model counts.
- `/cars/<slug>`: explicit generation/variant and reference year, manufacturer figures, linked gallery, engine/drivetrain narrative, structured specifications, source notes and related models.
- Brand previews: 100 ms pointer intent, 200 ms departure grace, direct brand/model links, keyboard focus, Escape, viewport positioning and a separate touch toggle. A native details menu and ordinary links remain usable without JavaScript.
- Gallery: native image links enhanced to a modal dialog, next/previous controls, arrow keys, Escape and focus restoration.
- Dashboard links now lead to the collection. Its mixed Ferrari/Lamborghini specification block is corrected to the 2017 Ferrari 812 Superfast. Other content and the SVG stay intact.
- CSP permits only same-origin scripts on dashboard/collection routes. Login/signup retain `script-src 'none'`. No third-party script, remote image, inline script or `unsafe-eval` permission was introduced.

## Design and research

The direction is an independent automotive editorial gallery: charcoal and graphite, warm off-white typography, generous alignment, a restrained red action colour, image-led compositions and consistent nested radii. System fonts avoid proprietary font redistribution. `corner-shape: squircle` is progressive enhancement; ordinary `border-radius` remains the fallback. The design works with decorative motion disabled.

Actual page content and structure were inspected using web retrieval, rather than copied:

| Reference | Adapted principle / inspection limit |
| --- | --- |
| [Apple iPhone](https://www.apple.com/iphone/) | Product-first introduction and clear routes into details; inspected content structure, not a live rendered layout. |
| [Apple motion](https://developer.apple.com/design/human-interface-guidelines/motion), [materials](https://developer.apple.com/design/human-interface-guidelines/materials) | Retrieval returned JavaScript shells. No claim of inspecting live guidance or interactions. Reduced motion and limited translucency follow this project’s brief. |
| [Polestar](https://www.polestar.com/) | Consistent per-model discovery; locale redirected to Belgium. No copying of imagery or navigation. |
| [Porsche 911](https://www.porsche.com/international/models/911/) | Distinguish variants and body styles before comparing specifications. |
| [Linear](https://linear.app/) | Concise information hierarchy and focused actions; live animation was not inspected. |
| [Lotus](https://www.lotuscars.com/) | Model-led storytelling. The extracted animated numbers were zeros: NaV12 deliberately renders final figures immediately. |
| [Road & Track](https://www.roadandtrack.com/) | Selective editorial emphasis, with a predictable catalogue beneath the feature. |

Avoided: cloned layouts, copied brand assets as interface decorations, scroll hijacking, animated counters, automatic carousels, hover-only navigation, pervasive glass, fake purchase/favourite controls, frameworks and animation libraries.

Motion uses 180 ms feedback and 280 ms panel/image transitions. Panels cancel pending timers; reduced-motion disables animation and transition effects. No guaranteed frame-rate claim is made.

## Files and dependencies

| File(s) | Purpose |
| --- | --- |
| `app.py` | Registers collection routes; narrowly selects script CSP. Account/storage logic unchanged. |
| `collection.py` | Read-only catalogue loader, protected routes, filtering and recovery pages. |
| `catalogue/vehicles.json` | Single vehicle/brand content source, including sources and verification notes. |
| `catalogue/assets.json` | Photo source, creator, licence, required credit, transformations and depicted model. |
| `templates/base.html` | Extension blocks, main landmark, local favicon and plain logout label. |
| `templates/dashboard.html` | Working brand menu/collection links; corrected Ferrari facts. |
| `templates/collection/` | Shared Jinja components and collection/brand/model/credits/404 pages. |
| `static/collection/` | Scoped tokens, styles, lightweight enhancement script, 44 responsive photo files. |
| `static/favicon.svg` | Original simple NaV12 mark. |
| `tests/` | Isolated server regression tests and browser review script. |
| `docs/` | Specification audit and final test evidence. |

No runtime dependencies changed. Existing pinned Flask, OpenPyXL and Gunicorn requirements remain. Browser QA used Python Playwright 1.62.0 and installed system Chromium. Playwright is optional development tooling, not a runtime requirement. `SOURCE_CODE.md` is the baseline’s older combined snapshot; the actual Python/templates/static files are authoritative for this update.

## Run safely in a separate local copy

Python 3.11+ on Linux/macOS; Windows requires WSL because existing storage uses `fcntl`.

Extract the source ZIP into a new directory. From its `nav12/` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p work/review-accounts
DATA_DIR="$PWD/work/review-accounts" PORT=5002 python app.py
```

Open `http://127.0.0.1:5002/signup`, create a disposable account, log in and select **Explore the collection**. This starts a local development server only. Do not use the production workbook for review. The existing app generates a temporary development signing key at restart, so sign in again after restarting.

For applying the supplied patch to an existing **clean isolated clone at the baseline commit**:

```bash
git switch -c feature/automotive-gallery
git apply --check /absolute/path/nav12-collection.patch
git apply /absolute/path/nav12-collection.patch
```

If the check fails, stop and compare your changes; do not force overwrite them. The patch includes binary media and all added source files. Existing deployment configuration, production environment values and the account data path require no change for the gallery.

## Tests

Server regression suite creates a `TemporaryDirectory` and sets `DATA_DIR` before app import:

```bash
python -m unittest discover -s tests -v
node --check static/collection/collection.js
```

For browser QA, keep the disposable-data server running on port 5002 in one terminal. In another, install optional test tooling and run:

```bash
python -m pip install playwright==1.62.0
python -m playwright install chromium
CHROMIUM_PATH="$(python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()')" \
NAV12_TEST_URL=http://127.0.0.1:5002 \
NAV12_QA_OUTPUT=work/browser-review \
python tests/browser_review.py
```

Alternatively set `CHROMIUM_PATH` to an installed Chrome/Chromium executable. Linux browser dependencies may need your platform’s normal installation step. The QA script registers synthetic users on the supplied server; use only disposable storage. Test results and screenshots are written to `NAV12_QA_OUTPUT`. The script does not submit anything to the live website.

Actual final results: **11/11 server tests and 19/19 browser checks passed**. Chromium 151.0.7922.173; no console errors or failed requests in normal flows. The intentionally aborted image test was isolated from that count. Widths: 360, 390, 768, 1280 and 1920 px; long model labels and 200% CSS layout zoom passed overflow checks. A single warm-cache local navigation measured 61.8 ms to DOMContentLoaded. Hover-to-visible under 4× CPU throttling measured 245.8 ms, including the deliberate hover delay and automation overhead. These are host observations, not field performance or frame-rate guarantees.

Executed in this workspace:

```text
DATA_DIR=/workspace/work/baseline-accounts PORT=5001 /workspace/nav12/.venv/bin/python app.py
python /workspace/work/baseline_browser.py
/workspace/nav12/.venv/bin/python -m unittest discover -s tests -v
NAV12_QA_OUTPUT=/workspace/work/screenshots python tests/browser_review.py
node --check static/collection/collection.js
git diff --check
```

The updated browser server used `DATA_DIR=/workspace/work/gallery-accounts`, port 5002. Final preservation checks compared the V12 SVG bytes and unchanged auth templates/styles/deployment files directly against the baseline Git blobs.

See `docs/test-results.json`, `docs/server-tests.txt` and the delivered screenshots for actual outcomes. Browser UI zoom, screen-reader output and physical mobile devices require a manual pass; automated QA exercises 200% CSS layout zoom, keyboard focus, reduced motion and mobile emulation.

## Remaining limitations

1. **Photography is not complete.** No exact usable photographs were obtained for AMG GT 63 C192, BMW M4 Competition G82 RWD, Audi R8 performance quattro facelift coupé, Aston Martin DB12 coupé, or 2021 W12 Continental GT Speed. Their deliberate temporary frames say so. These media-dependent pages are not claimed to be visually finished.
2. Eleven photographs cover five cars; most models do not yet have cabin/engine images. Some exterior photos cannot independently establish transmission or production year. Model pages distinguish photo equipment from the reference specification.
3. At your subsequent request, nine photos with unverified reuse rights are included for local review. Two photos have primary CC BY-SA 4.0 attribution verified through web retrieval. The manifest and credits page retain this distinction; a public repository alone conveys no photo licence.
4. Exact displacement remains **Not verified** for DB12, Bentley GT Speed and Chiron. The original Chiron’s launch acceleration is also **Not verified**. Some manufacturer pages required indexed primary text because full pages blocked retrieval. Details appear in each model’s source note and the specification audit.
5. Chromium was available for browser testing. Firefox/WebKit binaries were unavailable; their engine-specific appearance and behavior remain untested. Headless cloud rendering is not a physical mid-range-device benchmark.
6. The original V12 is an SVG illustration, not an interactive 3D model. This update does not pretend otherwise.

To complete the visual edition, add exact-variant licensed photographs to `static/collection/media/`, record them in `catalogue/assets.json`, and list their asset IDs in each vehicle’s `images`. Use the existing 480/960/1600 WebP and JPEG fallback convention. Recheck the four unverified facts against variant-specific manufacturer technical sheets, then run the tests and visually review the affected pages. For Firefox/WebKit, install those Playwright browsers and run equivalent navigation, touch/focus and screenshot checks. Manually check actual 200% browser zoom, VoiceOver/NVDA and physical Safari/Android Chrome before any separately authorised release.

## Rollback

The original checkout is untouched: simply stop the development server and discard the isolated review copy if you do not want the update. To undo an applied patch while keeping unrelated work:

```bash
git apply --reverse --check /absolute/path/nav12-collection.patch
git apply --reverse /absolute/path/nav12-collection.patch
```

Do not run the reverse patch over later edits without reviewing conflicts. Neither direction changes Excel data, production secrets or deployment configuration. No push, merge or deployment is part of this delivery.
