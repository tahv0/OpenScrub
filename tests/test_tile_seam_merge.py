"""Tiled detection must not split one object into seam-cut pieces.

Geometry below is the detector output replayed from a real 4K plate
frame (3x3 tiles, 608 input): the full-frame pass found the plate at
0.875, five tiles each returned a box cut at a seam, and the
highest-scoring piece used to suppress the full box.
"""
import numpy as np

import openscrub

W, H = 3840, 2160


def _tile_grid():
    """Tile rectangles of the 3x3 grid _maybe_tiled uses on a 4K frame."""
    th, tw = H // 3, W // 3
    oy, ox = int(th * 0.15), int(tw * 0.15)
    out = {}
    for gy in range(3):
        for gx in range(3):
            x1, y1 = max(0, gx * tw - ox), max(0, gy * th - oy)
            x2, y2 = min(W, (gx + 1) * tw + ox), min(H, (gy + 1) * th + oy)
            out[(gx, gy)] = (x1, y1, x2, y2)
    return out


TILES = _tile_grid()


def _finder(full, per_tile):
    """find_fn returning `full` on the whole frame and the frame-coordinate
    boxes in `per_tile[(gx, gy)]` converted to that tile's local coords."""
    def find(img):
        if img.shape[:2] == (H, W):
            return list(full)
        # identify the tile by call order (row-major, as _maybe_tiled loops)
        key = find.order[find.calls]
        find.calls += 1
        x1, y1 = TILES[key][:2]
        return [(b[0] - x1, b[1] - y1, b[2] - x1, b[3] - y1) + tuple(b[4:])
                for b in per_tile.get(key, [])]
    find.order = [(gx, gy) for gy in range(3) for gx in range(3)]
    find.calls = 0
    return find


def _covers(boxes, target):
    return any(b[0] <= target[0] + 0.5 and b[1] <= target[1] + 0.5
               and b[2] >= target[2] - 0.5 and b[3] >= target[3] - 0.5 for b in boxes)


def test_seam_pieces_merge_into_one_box_that_covers_the_full_detection():
    full = [(1213.7, 1172.9, 2680.4, 1791.3, 0.875)]
    per_tile = {
        (1, 1): [(1194.9, 1207.1, 2673.7, 1548.0, 0.928)],
        (2, 1): [(2368.0, 1195.8, 2586.0, 1548.0, 0.915)],
        (0, 2): [(1289.2, 1332.0, 1472.0, 1763.8, 0.883)],
        (1, 2): [(1195.1, 1332.0, 2683.1, 1771.4, 0.962)],
        (2, 2): [(2368.0, 1332.0, 2590.0, 1694.1, 0.839)],
    }
    frame = np.zeros((H, W, 3), np.uint8)
    rows = openscrub._maybe_tiled(_finder(full, per_tile), frame, 608, "auto")
    assert len(rows) == 1, rows
    assert _covers(rows, full[0][:4]), "the full-frame box must never be lost"
    for pieces in per_tile.values():
        for p in pieces:
            assert _covers(rows, p[:4]), "every piece's pixels stay covered"
    assert rows[0][4] == 0.962


def test_pieces_from_neighbouring_tiles_join_when_the_full_pass_missed():
    per_tile = {
        (0, 1): [(852.9, 758.0, 1472.0, 1301.9, 0.41)],
        (1, 1): [(1088.0, 766.7, 1844.6, 1359.6, 0.891)],
    }
    frame = np.zeros((H, W, 3), np.uint8)
    rows = openscrub._maybe_tiled(_finder([], per_tile), frame, 608, "auto")
    assert len(rows) == 1, rows
    assert rows[0][:4] == (852.9, 758.0, 1844.6, 1359.6)


def test_uncut_tile_boxes_and_separate_objects_keep_plain_nms():
    full = [(100.0, 100.0, 300.0, 160.0, 0.9), (3000.0, 1800.0, 3200.0, 1860.0, 0.8)]
    per_tile = {(0, 0): [(102.0, 101.0, 301.0, 161.0, 0.95)],      # duplicate, not cut
                (2, 2): [(2600.0, 1500.0, 2700.0, 1540.0, 0.7)]}   # separate, not cut
    frame = np.zeros((H, W, 3), np.uint8)
    rows = openscrub._maybe_tiled(_finder(full, per_tile), frame, 608, "auto")
    boxes = sorted(r[:4] for r in rows)
    assert boxes == sorted([(102.0, 101.0, 301.0, 161.0), (3000.0, 1800.0, 3200.0, 1860.0),
                            (2600.0, 1500.0, 2700.0, 1540.0)])


def test_cut_rows_with_silhouette_tails_are_left_to_plain_nms():
    full = [(1213.7, 1172.9, 2680.4, 1791.3, 0.5, ((0.1, 0.1),), 0)]
    per_tile = {(1, 2): [(1195.1, 1332.0, 2683.1, 1771.4, 0.9, ((0.2, 0.2),), 0)]}
    frame = np.zeros((H, W, 3), np.uint8)
    rows = openscrub._maybe_tiled(_finder(full, per_tile), frame, 608, "auto")
    assert [r[:4] for r in rows] == [(1195.1, 1332.0, 2683.1, 1771.4)]
    assert rows[0][5] == ((0.2, 0.2),)
