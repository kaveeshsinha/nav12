# NaV12 Engine Study

A public `/engine` experience introduces NaV12 through an original illustrative 65° V12 model. The dashboard and account navigation link to it; the existing catalogue, account storage and Garage keep their current routes and authentication.

## Experience

- Five native-scroll chapters: ignition, architecture, breathing, mechanical rhythm and the Ferrari 812 Superfast.
- A single Three.js scene with authored camera positions, local studio reflections and small pointer reactions.
- Free inspection by pointer, keyboard arrows or on-screen rotate controls; Escape or Return to story exits. Scrolling into another chapter returns to the guided camera.
- An optional slow airflow overlay. It is explanatory, not a combustion/firing-order simulation.
- An opt-in synthesized ignition atmosphere, muted when the tab becomes hidden. It is not a Ferrari recording.
- Native fullscreen dialog navigation, chapter links, keyboard focus, and both OS and in-page reduced-motion support.
- Matching desktop/mobile still renders when motion is reduced, JavaScript is disabled, or WebGL fails. Original model; not manufacturer CAD.

## Files and dependencies

`static/engine/engine-model.js` constructs the complete model from reusable geometry. `engine-scene.js` handles the camera and rendering, and `engine.js` handles the page controls. `templates/engine.html` is a standalone cinematic shell. `engine-teaser.css` scopes the dashboard entry styling.

Three.js 0.170.0 and its MIT license are vendored locally. Barlow Condensed Semibold is local with its OFL license. No CDN or additional production Python dependencies are required. The server permits only same-origin scripts on the new page.

The three WebP posters are offline renders of the same model geometry. They approximate the browser studio lighting. The 812 photo and specifications reuse the existing catalogue, including its original photography credits. 8,500 rpm is explicitly the engine speed at the quoted power output, not a universal V12 redline.

## Verification

- `python -m unittest discover -s tests -v`: 77 tests passed, including public engine access, protected member routes, dashboard integration and CSP regression checks.
- JavaScript syntax and model construction/update/disposal checks passed.
- Mesh-vertex camera projection checks cover desktop, portrait tablet, narrow phones, all chapter poses and free rotation.
- Desktop and 390-pixel mobile layouts, chapter links, fullscreen menu, Escape and reduced-motion controls reviewed in the preview browser.
- The preview browser disables WebGL. Live GPU rendering and drag/airflow animation require a final check in a WebGL-enabled browser. The static fallback was verified instead; the geometry was also rendered offline.

## Local use

Install `requirements.txt`, then run `python app.py` and open `/engine`. Use a disposable local database for development; never copy production account data into this repository.

## Regenerating the engine posters

See [`scripts/engine-posters/README.md`](scripts/engine-posters/README.md) for the portable offline renderer, exact maintenance dependencies and command. It exports the same procedural model, recreates all three WebP posters, and removes its intermediate geometry automatically. These tools are separate from the production application.
