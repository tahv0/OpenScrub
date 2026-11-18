# Check polygon media prerequisites before fixture allocation

The polygon actual-render fixture currently checks only ffmpeg, then fails during setup when ffprobe or the exact libx264/libx265 encoders are absent. Check both executables and one bounded encoder query before allocating its root or raw media, with clear skips for missing prerequisites. Keep real encoding and render/oracle failures visible.

Only tests/test_polygon_fallback.py changes. Nine helper contracts cover missing tools, unavailable queries, exact encoder names (including libx264rgb), skip-before-allocation and complete support. Genuine RED was captured before the helper checks; focused GREEN passes. The complete owning file passes on actual Python 3.12.16 and 3.9.25: 557 tests each, including all 14 real-media cases, with zero skips. Production behavior, fixture settings and existing paint/render assertions are unchanged.

Validation: clean frozen candidate c7f9dcc29affe5da363094b8646b3064966e52ed over a3c3193e8dff41ec0588e66443398048a5c15ece; diff check, Python 3.9 grammar, recursive sdist inclusion and all-other-tracked-byte equality verified. Independent review pending; this is a local PR draft and has not been published.
