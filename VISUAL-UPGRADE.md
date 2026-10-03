# ScholarScout — animated visual edition

This is the original ScholarScout project with a separate visual enhancement layer.
The backend, original application controller, research records, agent workflow,
approval controls, and email-sending logic are unchanged.

## Run locally

```sh
python -m pip install -r requirements.txt
playwright install chromium
python run.py
```

Open http://127.0.0.1:8001. Configure your own AI/search providers through the
existing settings. No API credentials, databases, or research results are bundled.
The original repository omitted `python-multipart`, required by its CV-upload
route at startup. This dependency has been added to requirements.txt.

## Added visuals

- A rotating, real WebGL globe with land geometry, grid lines, and orbital accents.
- A selectable procedural 3D university with columns, steps, a dome, glass research
  wing, and trees. Both models support pointer dragging and keyboard arrow keys.
- An original AI-generated campus image, used in an editorial panel and screen headers.
- Consistent SVG metric, navigation, and empty-state graphics.
- Subtle screen transitions, card hover effects, and real-value update highlights.
- Responsive hero and metric layouts, persistent pause preference, reduced-motion
  support, offscreen/hidden-tab rendering suspension, and static-image fallback.

The models and campus image are decorative concepts, not verified institutions,
research results, or a visualization of the user's current research coverage.

## Files and customization

- `static/css/visuals.css`: visual styles, colors, responsive rules, motion treatment.
- `static/js/visuals.js`: procedural model geometry, animation, controls and SVGs.
- `static/index.html`: added hero, illustration panel, and visual asset includes.
- `static/assets/research-campus.webp`: optimized generated campus illustration.
- `static/assets/land.geojson`: local land polygons for the globe.
- `static/vendor/three.min.js`: local Three.js, so visuals do not need a CDN.

Use the original `styles.css` and `app.js` for existing application behavior.
To remove the visual layer, remove its two includes and the added hero/figure
markup in index.html; none of the backend depends on it.

## Asset provenance

- Three.js 0.160.0 — MIT; license included in `static/vendor/THREE-LICENSE.txt`.
  Source: https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js
- Natural Earth 1:110m land — public domain.
  Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson
  Terms: https://www.naturalearthdata.com/about/terms-of-use/
- Research campus — created using the built-in image-generation tool for this project.
  Prompt: "A sculptural miniature ivory university building with classical columns
  and a modern glass laboratory wing on a floating circular navy plinth, one floating
  open book and delicate metallic orbital arcs. Sophisticated architectural scale
  model, frosted glass, porcelain, brushed champagne metal, soft teal luminous accents.
  Dark midnight navy seamless studio background #091c29, subtle volumetric light,
  cinematic precise shadows, premium product visualization. Building centered,
  ample clean dark negative space around silhouette. No letters, logos, interface,
  labels, or people. Wide 1536x1024 editorial 3D illustration."
- Procedural campus model and interface SVGs — implemented directly in visuals.js.

## Validation

- Existing `test_health.py` and `test_dashboard_routes.py`: 7 tests passed against
  an isolated temporary database.
- Chromium: 3D rendering, model switch, motion toggle, agent modal launch,
  university navigation, reduced-motion preference, and missing-3D-library fallback.
- Overview has no horizontal page overflow at widths 320, 390, and 768 pixels.
- All ten screens remain navigable at 390px without horizontal page overflow.
- No browser JavaScript exceptions observed during these checks.
- Live paid AI/search requests and external email delivery were not exercised.

Screenshots are included under `preview/`. The original GitHub repository has not
been pushed or deployed by this update.
