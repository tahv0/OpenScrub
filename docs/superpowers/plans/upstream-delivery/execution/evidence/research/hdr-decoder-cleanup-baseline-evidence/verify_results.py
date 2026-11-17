#!/usr/bin/env python3
"""Verify retained research evidence, not an application regression suite."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
r = json.loads((root / 'results.json').read_text())
cases = {c['name']: c for c in r['cases']}
assert r['fixture_decoded_all_3_frames_exact']
assert len(cases) == 10

def decoder(c, phase='at_return_or_held_traceback'):
    return next(p for p in c[phase]['children'] if 'pipe:1' in p['command'])

def terminal(snapshot):
    for p in snapshot['children']:
        assert p['proc_state'] == 'absent', p
        assert p['wait_returns'], p  # actual wait returned, not just kill(pid, 0)
        for s in p['streams']:
            assert s['closed'] is not False, s
            # A numeric descriptor may be reused by ff_err; compare pipe identity.
            assert not (s['fd_state']['open'] and s['fd_state']['same_target']), s
    for s in snapshot['temporary_files']:
        assert s['closed'] is not False, s
        assert not (s['fd_state']['open'] and s['fd_state']['same_target']), s

for label in ['baseline', 'donor']:
    for kind in ['cancel', 'encoder-exit']:
        c = cases[label + '-' + kind + '-weak-observer']
        assert c['status'] == ('PipelineCancelled' if kind == 'cancel' else 'RuntimeError')
        d = decoder(c)
        assert d['proc_state'] == 'absent' and d['wait_returns']
        stream = d['streams'][0]
        assert stream['closed'] == (label == 'donor')
        assert stream['fd_state']['open'] == (label == 'baseline')
        if kind == 'encoder-exit':
            assert 'BrokenPipeError' in c['traceback'] and 'enc.stdin.write(buf.tobytes())' in c['traceback']
            assert c['encoder_write_attempt_frames'] == 1
        terminal(c['after_releasing_exception_and_gc'])
    io = cases[label + '-io-error-weak-observer']
    assert io['status'] == 'RuntimeError' and 'No such file or directory' in io['message']
    assert 'BrokenPipeError' not in io['traceback']
    assert decoder(io)['streams'][0]['closed'] is True

for c in cases.values():
    terminal(c['terminal_after_harness_cleanup'])
    if c['status'] == 'success':
        assert c['preencode_all_3_frames_equal_source_raw']
        assert c['encoder_write_attempt_frames'] == c['decoded_frame_count'] == 3
        s = c['metadata']['streams'][0]
        assert (s['codec_name'], s['pix_fmt'], s['color_space'], s['color_transfer'], s['color_primaries']) == (
            'hevc', 'yuv420p10le', 'bt2020nc', 'smpte2084', 'bt2020')
        assert s['nb_read_frames'] == '3'
        assert not c['harness_cleanup_actions']
    if not c['strong_diagnostic_popen_references']:
        assert not c['harness_cleanup_actions']

strong = cases['baseline-cancel-diagnostic-strong']
assert decoder(strong, 'after_releasing_exception_and_gc')['streams'][0]['closed'] is False
assert [a['action'] for a in strong['harness_cleanup_actions']] == ['harness close stdout']
terminal(r['fixture_tools_terminal'])
terminal(r['output_tools_terminal'])
children = sum(len(c['terminal_after_harness_cleanup']['children']) for c in cases.values())
children += len(r['fixture_tools_terminal']['children']) + len(r['output_tools_terminal']['children'])
print(json.dumps({'verified': True, 'cases': len(cases), 'children_all_waited_and_absent': children,
    'baseline_missing_close_reproductions': ['callback cancellation', 'real encoder write BrokenPipeError'],
    'donor_closes_decoder_in_both': True,
    'weak_observer_resources_released_after_exception_release': True,
    'diagnostic_strong_reference_required_harness_close': True}, indent=2))
