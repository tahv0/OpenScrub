#!/usr/bin/env python3
"""Verify the recorded reproduction outcomes without rerendering media."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
r = json.loads((root / 'results.json').read_text())
cases = r['chroma']['cases']
assert len(cases) == 48
assert r['chroma']['donor_tip_full_square_fixture_pass'] == {'baseline': True, 'donor': True}
for case in cases:
    d = case['implementations']['donor']
    assert not d['missing_cells_yx'] and not d['extra_cells_yx']
    assert d['luma_same_as_baseline'] and d['uv_same_coverage'] and d['unrelated_chroma_unchanged']
missing = sum(bool(c['implementations']['baseline']['missing_cells_yx']) for c in cases)
extra = sum(bool(c['implementations']['baseline']['extra_cells_yx']) for c in cases)
assert (missing, extra) == (26, 1)
for name, exception in [('nan_point', 'ValueError'), ('infinite_point', 'OverflowError'),
                        ('missing_coordinate', 'ValueError'), ('extra_coordinate', 'ValueError'),
                        ('nonnumeric_coordinate', 'ValueError')]:
    for path in ['sdr', 'hdr']:
        assert r['geometry'][name]['baseline'][path]['status'] == exception
        assert r['geometry'][name]['donor'][path]['full_box']
for name in ['two_points', 'empty_polygon', 'outside_empty']:
    assert all(r['geometry'][name]['baseline'][p]['full_box'] for p in ['sdr', 'hdr'])
for name in ['collinear', 'repeated_point']:
    for path in ['sdr', 'hdr']:
        assert not r['geometry'][name]['baseline'][path]['full_box']
        assert r['geometry'][name]['donor'][path]['full_box']
for label in ['baseline', 'donor']:
    for path in ['sdr', 'hdr']:
        assert r['geometry']['nan_region'][label][path]['status'] == 'ValueError'
        assert not any(r['geometry']['reversed_region'][label][path]['changed'])
media = r['media']
assert all(media['source_plane_exact'])
for name in ['sparse_baseline', 'sparse_donor_leaf']:
    m = media['cases'][name]
    assert m['status'] == 'ok'
    st = m['output_metadata']['streams'][0]
    assert [st[k] for k in ['codec_name', 'pix_fmt', 'color_space', 'color_transfer', 'color_primaries', 'nb_frames']] == [
        'hevc', 'yuv420p10le', 'bt2020nc', 'smpte2084', 'bt2020', '3']
    assert all(m['preencode_exact_leaf_match']) and m['preencode_unrelated_chroma_unchanged']
    assert m['preencode_luma_pixels_yx'] == [[5, 6], [5, 7], [6, 6]]
assert media['cases']['sparse_baseline']['preencode_u_at_required'] == [800, 512]
assert media['cases']['sparse_baseline']['preencode_v_at_required'] == [300, 512]
assert media['cases']['sparse_donor_leaf']['preencode_u_at_required'] == [512, 512]
assert media['cases']['sparse_donor_leaf']['preencode_v_at_required'] == [512, 512]
for name, exception in [('nan_point', 'ValueError'), ('infinite_point', 'OverflowError'),
                        ('malformed_point', 'ValueError'), ('nan_box', 'ValueError')]:
    assert media['cases'][name]['status'] == exception
assert media['cases']['two_points']['preencode_changed_pixels'] == [144, 36, 36]
assert media['cases']['collinear']['preencode_changed_pixels'] == [12, 6, 6]
assert media['cases']['reversed_box']['preencode_changed_pixels'] == [0, 0, 0]
summary = {'verified': True, 'chroma_cases': len(cases), 'baseline_missing_coverage_cases': missing,
           'baseline_extra_coverage_cases': extra, 'donor_chroma_failures': 0,
           'geometry_cases_each_in_sdr_and_hdr': len(r['geometry']),
           'real_hdr_render_cases': len(media['cases']),
           'n02_disposition': 'confirmed; minimal chroma coverage contract',
           'n03_disposition': 'confirmed valid-box reliability/degeneracy candidate; existing empty-mask fallbacks retained; invalid boxes require explicit render failure'}
print(json.dumps(summary, indent=2))
