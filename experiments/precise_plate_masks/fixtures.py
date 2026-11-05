"""Deterministic, wholly synthetic fixtures for a throwaway mask comparison.

These toy scenes test geometry and mask accounting, not real-world generalization.
Frames are uint8 BGR, 480 pixels wide by 320 high. Masks are bool arrays in
frame coordinates. Detector boxes use exclusive (x1, y1, x2, y2) bounds and
include 8% of the full plate's bounding-box size on EACH side, clipped to the
frame. No render padding is applied here. All lettering is invented test text.
text_mask targets visible main glyphs, including antialiased edge support;
it excludes the plate border, background, and small decorative TEST caption.
"""

from dataclasses import dataclass

import cv2
import numpy as np


WIDTH, HEIGHT = 480, 320


@dataclass
class PlateCase:
    """Full plate includes hidden pixels; visible plate excludes foreground."""

    name: str
    frame: np.ndarray
    visible_mask: np.ndarray
    full_mask: np.ndarray
    detector_box: tuple[int, int, int, int]
    note: str
    text_mask: np.ndarray | None = None


def _scene(seed: int, offset: int = 0) -> np.ndarray:
    """Draw a textured toy car in an invented outdoor scene, in BGR order."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:HEIGHT, :WIDTH]
    sky = np.stack((168 - yy * .12, 154 - yy * .10, 133 - yy * .08), -1)
    sky += rng.normal(0, 2.1, sky.shape)
    frame = np.clip(sky, 0, 255).astype(np.uint8)
    cv2.rectangle(frame, (0, 148), (479, 319), (61, 66, 68), -1)
    cv2.line(frame, (8, 293), (125, 293), (162, 164, 161), 4)
    cv2.line(frame, (355, 293), (472, 293), (162, 164, 161), 4)
    cv2.ellipse(frame, (240 + offset, 280), (190, 15), 0, 0, 360, (34, 36, 38), -1)
    for x in (105, 371):
        cv2.ellipse(frame, (x + offset, 258), (24, 35), 0, 0, 360, (21, 23, 24), -1)
    body = np.zeros((HEIGHT, WIDTH), np.uint8)
    pts = np.array([(62, 263), (66, 175), (112, 151), (144, 96),
                    (333, 96), (372, 151), (411, 179), (418, 264)], np.int32)
    pts[:, 0] += offset
    cv2.fillPoly(body, [pts], 255)
    paint = np.stack((137 - yy * .15 + xx * .015,
                      107 - yy * .13, 78 - yy * .10 + xx * .01), -1)
    paint += rng.normal(0, 1.8, paint.shape)
    frame[body != 0] = np.clip(paint[body != 0], 0, 255).astype(np.uint8)
    window = np.array([(151, 105), (326, 105), (351, 151), (128, 151)], np.int32)
    window[:, 0] += offset
    cv2.fillPoly(frame, [window], (63, 60, 53))
    cv2.polylines(frame, [window], True, (153, 143, 124), 2, cv2.LINE_AA)
    cv2.line(frame, (92 + offset, 173), (390 + offset, 173), (160, 124, 91), 2)
    cv2.rectangle(frame, (87 + offset, 187), (132 + offset, 209), (83, 102, 182), -1)
    cv2.rectangle(frame, (350 + offset, 187), (394 + offset, 209), (83, 102, 182), -1)
    cv2.rectangle(frame, (83 + offset, 268), (396 + offset, 275), (52, 54, 55), -1)
    cv2.line(frame, (87 + offset, 270), (392 + offset, 270), (133, 135, 135), 1)
    return frame


def _main_lettering(layout: str) -> tuple[tuple[str, tuple[int, int], float, int], ...]:
    if layout == "single":
        return (("DEMO", (15, 46), 1.32, 2),)
    if layout == "two_rows":
        return (("DEMO", (43, 33), .70, 1), ("123", (64, 55), .65, 1))
    if layout == "hyphen":
        return (("TEST-00", (8, 46), .98, 2),)
    raise ValueError(f"Unknown synthetic lettering layout: {layout}")


def _glyph_mask(layout: str) -> np.ndarray:
    mask = np.zeros((64, 176), np.uint8)
    for text, origin, scale, thickness in _main_lettering(layout):
        cv2.putText(mask, text, origin, cv2.FONT_HERSHEY_SIMPLEX,
                    scale, 255, thickness, cv2.LINE_AA)
    return mask


def _plate(low_contrast: bool = False, lettering: str = "single") -> np.ndarray:
    """A synthetic rectangular plate texture, subsequently perspective warped."""
    yy, xx = np.mgrid[:64, :176]
    base = 145 if low_contrast else 221
    shade = base + xx * .035 - yy * .16 + 2 * np.sin(xx / 13)
    plate = np.repeat(shade[..., None], 3, axis=2)
    plate += np.random.default_rng(701).normal(0, .8, plate.shape)
    plate = np.clip(plate, 0, 255).astype(np.uint8)
    border = (116, 117, 115) if low_contrast else (80, 82, 76)
    ink = (117, 120, 118) if low_contrast else (33, 40, 31)
    cv2.rectangle(plate, (1, 1), (174, 62), border, 2)
    for text, origin, scale, thickness in _main_lettering(lettering):
        cv2.putText(plate, text, origin, cv2.FONT_HERSHEY_SIMPLEX,
                    scale, ink, thickness, cv2.LINE_AA)
    cv2.putText(plate, "TEST", (72, 12), cv2.FONT_HERSHEY_SIMPLEX,
                .27, ink, 1, cv2.LINE_AA)
    for x in (9, 166):
        cv2.circle(plate, (x, 8), 2, (103, 106, 101), -1)
    return plate


def _box(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("Synthetic fixture has an empty full plate mask")
    x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    px, py = int(np.ceil((x2 - x1) * .08)), int(np.ceil((y2 - y1) * .08))
    return max(0, x1 - px), max(0, y1 - py), min(WIDTH, x2 + px), min(HEIGHT, y2 + py)


def _make(name: str, quad: np.ndarray, *, occlusion: str = "", seed: int = 3,
          offset: int = 0, pole_x: int = 240, low_contrast: bool = False,
          glare: bool = False, note: str = "", lettering: str = "single") -> PlateCase:
    frame = _scene(seed, offset)
    source = np.float32([(0, 0), (175, 0), (175, 63), (0, 63)])
    transform = cv2.getPerspectiveTransform(source, np.float32(quad))
    warped = cv2.warpPerspective(_plate(low_contrast, lettering), transform, (WIDTH, HEIGHT))
    glyphs = cv2.warpPerspective(_glyph_mask(lettering), transform, (WIDTH, HEIGHT))
    support = cv2.warpPerspective(np.full((64, 176), 255, np.uint8), transform,
                                  (WIDTH, HEIGHT), flags=cv2.INTER_NEAREST)
    full = support != 0
    frame[full] = warped[full]
    if glare:
        yy, xx = np.mgrid[:HEIGHT, :WIDTH]
        glow = np.exp(-((xx - 270) ** 2 / 850 + (yy - 221) ** 2 / 270)) * .92
        mix = frame.astype(np.float32) * (1 - glow[..., None]) + 250 * glow[..., None]
        frame[full] = np.clip(mix[full], 0, 255).astype(np.uint8)
    foreground = np.zeros((HEIGHT, WIDTH), np.uint8)
    if occlusion == "cross":
        # Two foreground straps divide visible support into four components.
        cv2.rectangle(foreground, (230, 178), (248, 289), 255, -1)
        cv2.rectangle(foreground, (117, 226), (363, 237), 255, -1)
    elif occlusion == "hole":
        # A foreground circular object entirely inside the plate creates a hole.
        cv2.circle(foreground, (239, 231), 12, 255, -1)
    elif occlusion == "pole":
        cv2.rectangle(foreground, (pole_x, 125), (pole_x + 25, 319), 255, -1)
    elif occlusion:
        raise ValueError(f"Unknown synthetic occlusion: {occlusion}")
    cover = foreground != 0
    frame[cover] = (48, 78, 109)
    # Texture the foreground while using precisely the same rasterized support.
    if cover.any():
        yy, xx = np.mgrid[:HEIGHT, :WIDTH]
        texture = ((xx + yy) % 7).astype(np.uint8)
        frame[cover] += texture[cover, None]
    visible = full & ~cover
    return PlateCase(name, frame, visible, full, _box(full),
                     "SYNTHETIC geometry fixture; not generalization evidence. " + note,
                     text_mask=(glyphs != 0) & visible)


def make_cases() -> list[PlateCase]:
    """Return fresh, deterministic arrays; moving_occluder_* is one sequence."""
    straight = np.float32([(144, 202), (337, 202), (337, 266), (144, 266)])
    rotated = cv2.boxPoints(((240, 230), (194, 64), -17))
    # boxPoints starts at bottom-left; enforce TL, TR, BR, BL source ordering.
    rotated = rotated[[1, 2, 3, 0]]
    perspective = np.float32([(155, 197), (337, 214), (318, 264), (144, 254)])
    cases = [
        _make("frontal", straight, note="Frontal plate with textured paint."),
        _make("rotated", rotated, note="Plate rotated in the image plane by 17 degrees."),
        _make("perspective", perspective, note="Trapezoidal perspective and sloped edges."),
        _make("disconnected_cross_occlusion", straight, occlusion="cross",
              note="Two opaque straps; four disconnected visible plate components."),
        _make("interior_occluder_hole", straight, occlusion="hole",
              note="Opaque circular object; visible plate has an interior hole."),
        _make("low_contrast_glare", perspective, low_contrast=True, glare=True,
              note="Muted plate/ink contrast with a bright non-opaque glare patch."),
        _make("small_plate", np.float32([(216, 224), (272, 221), (274, 243), (216, 245)]),
              note="Small plate, about 58 by 24 pixels before detector padding."),
    ]
    for i, (shift, pole_x) in enumerate(((-9, 192), (0, 229), (9, 266))):
        cases.append(_make(f"moving_occluder_{i:02d}", straight + (shift, 0),
                           occlusion="pole", seed=19, offset=shift, pole_x=pole_x,
                           note=f"Sequence moving_occluder, frame {i}/2: car and pole shift."))
    cases.extend([
        _make("narrow_two_rows", np.float32([(157, 189), (324, 189), (324, 266), (157, 266)]),
              lettering="two_rows", note="Main target is two separate rows: DEMO / 123."),
        _make("narrow_hyphen", straight, lettering="hyphen",
              note="Main fictional target is TEST-00, including its hyphen."),
    ])
    return cases
