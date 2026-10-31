# Engine poster maintenance

These tools render the exact geometry from `static/engine/engine-model.js` into the three checked-in WebP fallback assets. They do not affect the production application or add production dependencies.

From any working directory, run the renderer by its path:

```sh
python scripts/engine-posters/render.py
```

The script invokes `export.mjs` with Node.js, creates the geometry JSON in an automatically cleaned temporary directory, and writes only:

- `static/engine/engine-poster.webp` — 1600 × 1000, engine right
- `static/engine/engine-poster-mobile.webp` — 800 × 1200, engine lower-center
- `static/engine/engine-teaser.webp` — 1200 × 900, engine centered

No intermediate JSON or PNG files are retained. The exporter imports the repository's vendored Three.js; Node.js needs no npm installation.

## Offline renderer dependencies

Tested with Python 3.12, Node.js 24, Mesa EGL / llvmpipe, and:

```sh
python -m pip install numpy==2.3.5 Pillow==12.3.0 moderngl==5.13.0 glcontext==3.1.0
```

A system EGL implementation is required (`libEGL` and a driver such as Mesa). Once those maintenance dependencies are installed, rendering requires no network access. Install them in a separate development environment, not in the web application's production environment.

The renderer uses physically based metallic shading, analytic studio reflection highlights, a shadow map and 2× supersampling. Its lighting approximates the browser scene; generating these stills does not verify WebGL runtime behavior. PNG/WebP encoder and GPU-driver differences can change output bytes slightly. The checked-in presets are defined at the end of `render.py`.
