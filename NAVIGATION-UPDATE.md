# NaV12 navigation update

This ZIP is the second local review version. It includes the complete application and the original collection update, plus the horizontal navigation and engine guide requested on 13 October 2026. Nothing has been pushed to GitHub or deployed.

## What changed

- One horizontal navigation row on the dashboard, collection, brand, model, credits and engine pages: **Car Brands · Engine Types · Driving Character · Powertrains**, followed by **All cars**.
- Car Brands is first, aligned to the left edge. Its existing brand list and hover, keyboard and touch previews remain available.
- Menus share spacing, typography, focus treatment and a restrained open state. One menu opens at a time; Escape and outside clicks dismiss it. On small screens the row scrolls horizontally, while menu panels fit the viewport and scroll vertically when necessary.
- Fourteen engine guide entries: naturally aspirated V12, twin-turbo V12, V12, V10, V8, V6, flat-six, inline-six, inline-four, W12, W16, naturally aspirated, turbocharged and supercharged.
- Cylinder layout, induction and powertrain are explained separately. BMW's inline-six is not labelled V6; Bentley's W12 is not labelled V12; the hybrid Revuelto remains a naturally aspirated V12.
- Engine pages link to matching existing cars. V6, twin-turbo V12, inline-four and supercharged pages explain the engineering and clearly state that no matching models are in this ten-car collection yet.
- Driving Character and Powertrains apply real collection filters with accurate counts. The new Engine type filter composes with brand, character, powertrain and search, persists in the URL, and works without JavaScript.
- Fixed an existing dashboard header overflow at narrow phone widths and used inline SVG arrows so the new icons do not depend on font glyph coverage.

## Run on Linux

Extract into a **new folder**, then open a terminal inside `nav12` beside `app.py`. Python 3.11 or later is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
APP_ENV=development DATA_DIR="$PWD/work/review-accounts" \
python -m flask --app app run --host 127.0.0.1 --port 5002
```

Open **http://127.0.0.1:5002/signup**, create a disposable account and sign in. Stop your previous local server with Ctrl+C first if it is using port 5002. This new folder starts with separate test accounts. Keep your previous extracted folder if you want to return to the earlier version. There is no need to move or overwrite any Excel workbook.

On Fedora, if Python or pip is missing, install the required packages with `sudo dnf install python3 python3-pip`. On Ubuntu/Debian, use `sudo apt install python3-venv python3-pip` if virtual environment creation reports missing support. Windows requires WSL because the existing Excel lock uses `fcntl`; macOS uses the same run commands as Linux.

## Test locally

In a second terminal in the same `nav12` folder:

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

The server tests use temporary account storage. Browser tests use the running development server; keep it pointed at the disposable accounts shown above.

```bash
python -m pip install playwright==1.62.0
python -m playwright install chromium
export CHROMIUM_PATH="$(python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()')"
NAV12_TEST_URL=http://127.0.0.1:5002 python tests/navigation_browser_review.py
NAV12_TEST_URL=http://127.0.0.1:5002 python tests/browser_review.py
```

On Linux, browser system dependencies may need the normal distribution package installation. Navigation screenshots and results are written to `work/navigation-review`; the original collection suite writes to `work/browser-review`.

## Design references

Navigation structure and text were inspected on [Polestar](https://www.polestar.com/us/), [Porsche](https://www.porsche.com/usa/) and [Lamborghini](https://www.lamborghini.com/en-en). The design uses their clear topic grouping and short routes into models as inspiration; it does not copy UI code or branding. Their rendered motion was not evaluated.

The extra sections are based on the current collection: driving character and powertrain create useful routes into real cars. Body Styles was not added because this collection's coupé focus would produce little choice. Future catalogue additions can make that category useful.

## Data and technical references

`catalogue/engines.json` contains guide copy, matching rules and a primary reference for every entry. `catalogue/vehicles.json` adds explicit `engine_layout`, `induction` and `turbo_count` fields, retaining existing model specifications and source links. Supporting sources include Porsche's flat-engine history, BMW M3/M4 engineering, Aston Martin's 2024 Vanquish launch, YASA's Ferrari 296 powertrain information and Eaton's supercharger explanation. Each engine page exposes its reference link.

Navigation is one shared Jinja macro. Native `details`/`summary`, ordinary links and server-rendered GET forms remain functional without JavaScript. The local script adds viewport positioning, mutual exclusion, dismissal and preview enhancements. No dependency or account/security/deployment setting changed for this revision; the original V12 SVG remains intact.

Photo coverage, rights labels and unverified specification fields from the first version are unchanged; see `COLLECTION-UPDATE.md` and `catalogue/assets.json`. No new photos or claimed vehicle specifications were added in this revision.

## Verification for this version

- **18 server tests passed**, including all engine guides, correct car membership, combined filters, unknown inputs and account/security regressions.
- **14 new navigation browser check groups passed** plus **19 existing collection browser check groups passed**, using Chromium 151.0.7922.173 with disposable accounts.
- Checked widths 360, 390, 768, 1280 and 1920 pixels, one-row navigation, viewport-fitted menus, keyboard/Tab/Escape, outside dismissal, retained brand previews, touch emulation, real filters and JavaScript-disabled browsing. No console errors or failed requests in the normal test contexts.
- Account application code, auth templates, original styles, dependencies and deployment files compared byte-for-byte with the previously delivered ZIP. The original V12 SVG is unchanged. The original `/workspace/nav12` checkout remains clean.
- Browser checks ran on Linux headless Chromium with emulated screen/touch settings. Physical phones, screen readers, Firefox and WebKit were not tested for this revision.

Receipts: `docs/server-tests.txt`, `docs/navigation-results.json` and `docs/test-results.json`.
