"""Ephemeral evidence from an explicitly requested fresh HDR tone-map.

No persisted report or cached intermediate is trusted to establish this pair.
Only a zero-origin, integer-rate, unrotated 10-bit HDR stream is qualified.
"""
from fractions import Fraction
import hashlib
import json
import os
import re
import subprocess
import tempfile

from openscrub_internal import exact_samples as exact

TONEMAP_VF = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
              "tonemap=tonemap=hable:desat=0,"
              "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def _stamp(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _current(path, stamp, opened=None):
    try:
        return (_stamp(os.stat(path)) == stamp
                and (opened is None or _stamp(os.fstat(opened.fileno())) == stamp))
    except OSError:
        return False


def _wait(process, cb, cancelled):
    try:
        while True:
            try:
                process.wait(timeout=.5)
                return process.returncode
            except subprocess.TimeoutExpired:
                if cb.cancelled():
                    raise cancelled()
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise


def _trace(log, fps, count, width, height, digest):
    """Validate every decoded/filter frame against the exact zero CFR grid."""
    clocks, seen = {}, {'before': 0, 'after': 0}
    for line in log:
        match = re.search(r'showinfo@(before|after)\s+@[^]]+\]', line)
        if not match:
            continue
        side = match.group(1)
        clock = re.search(r'config in time_base:\s*(\d+/\d+)', line)
        if clock:
            if side in clocks:
                return False
            clocks[side] = Fraction(clock.group(1))
            if clocks[side] <= 0:
                return False
            continue
        frame = re.search(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+).*?\bs:(\d+)x(\d+)', line)
        if not frame:
            continue
        index, pts, w, h = map(int, frame.groups())
        if (side not in clocks or index != seen[side] or index >= count
                or (w, h) != (width, height)
                or Fraction(pts) * clocks[side] != Fraction(index, fps)):
            return False
        digest.update((side + ':' + line[match.end():].strip() + '\n').encode('utf-8'))
        seen[side] += 1
    return seen == {'before': count, 'after': count}


def _packets(path, fps, count, cb, cancelled, digest):
    metadata = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=time_base', '-of', 'json', path],
        capture_output=True, check=True, timeout=15)
    tick = Fraction(json.loads(metadata.stdout)['streams'][0]['time_base'])
    if tick <= 0:
        return False
    with tempfile.TemporaryFile(mode='w+t') as packet_log:
        process = subprocess.Popen(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_packets', '-show_entries', 'packet=pts', '-of', 'csv=p=0', path],
            stdout=packet_log, stderr=subprocess.DEVNULL)
        if _wait(process, cb, cancelled) != 0:
            return False
        packet_log.seek(0)
        index = 0
        for line in packet_log:
            value = line.strip()
            if not value:
                continue
            if (not re.fullmatch(r'-?\d+', value) or index >= count
                    or Fraction(int(value)) * tick != Fraction(index, fps)):
                return False
            digest.update(('packet:%d:%s:%s\n' % (index, value, tick)).encode('ascii'))
            index += 1
        return index == count


def fresh_tonemap(source, output, cb, cancelled):
    """Produce an optional proof only for this newly encoded source/copy pair.

    Source and filter output frame PTS are traced during the normal conversion;
    encoded packet PTS are checked without another video decode. CPU H.264 with
    no B frames gives one timestamped packet per frame in presentation order.
    """
    source, output = os.path.realpath(source), os.path.realpath(output)
    try:
        alias = os.path.samefile(source, output)
    except FileNotFoundError:
        alias = source == output
    if alias:
        raise RuntimeError('HDR scan copy cannot alias source')
    stage = None
    try:
        with open(source, 'rb') as src:
            source_stamp = _stamp(os.fstat(src.fileno()))
            if not _current(source, source_stamp, src):
                return None
            facts = exact.probe_source(source)
            fps, count = facts['rate'], facts['count']
            if (not _current(source, source_stamp, src)
                    or facts['pixel_format'] != 'yuv420p10le'
                    or facts['color_transfer'].lower() not in ('smpte2084', 'arib-std-b67')
                    or not fps.is_integer() or not 1 <= fps <= 120 or count is None
                    or facts['width'] % 2 or facts['height'] % 2):
                return None
            fps = int(fps)
            fd, stage = tempfile.mkstemp(prefix='.hdr-quad-', suffix='.mp4',
                                         dir=os.path.dirname(output))
            with os.fdopen(fd, 'w+b') as copied:
                return _fresh_encode(src, source, source_stamp, output, copied, stage,
                                     facts, fps, count, cb, cancelled)
    except (exact.ExactError, OSError, subprocess.SubprocessError, ValueError,
            KeyError, TypeError, ZeroDivisionError):
        return None
    finally:
        if stage is not None:
            try:
                os.unlink(stage)
            except FileNotFoundError:
                pass


def _fresh_encode(src, source, source_stamp, output, copied, stage, facts, fps, count, cb, cancelled):
    stage_inode = _stamp(os.fstat(copied.fileno()))[:2]
    filters = 'showinfo@before,' + TONEMAP_VF + ',showinfo@after'
    with tempfile.TemporaryFile(mode='w+t') as log:
        command = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'info', '-copyts',
            '-i', source, '-fps_mode', 'passthrough', '-vf', filters,
            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-pix_fmt', 'yuv420p',
            '-bf', '0', '-c:a', 'copy', stage]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        if _wait(process, cb, cancelled) != 0:
            return None
        scan_stamp = _stamp(os.fstat(copied.fileno()))
        if (scan_stamp[:2] != stage_inode or not _current(stage, scan_stamp, copied)
                or not _current(source, source_stamp, src)):
            return None
        scan = exact.probe_source(stage)
        if (scan['width'] != facts['width'] or scan['height'] != facts['height']
                or scan['rate'] != fps or scan['count'] != count
                or scan['pixel_format'] != 'yuv420p'
                or scan['color_transfer'].lower() != 'bt709'
                or scan['color_primaries'].lower() != 'bt709'):
            return None
        log.seek(0)
        digest = hashlib.sha256(b'openscrub-hdr-quad-trace-v1:')
        if (not _trace(log, fps, count, facts['width'], facts['height'], digest)
                or not _packets(stage, fps, count, cb, cancelled, digest)
                or not _current(stage, scan_stamp, copied)
                or not _current(source, source_stamp, src)):
            return None
        source_hash = hashlib.sha256()
        for block in iter(lambda: src.read(1 << 20), b''):
            if cb.cancelled():
                raise cancelled()
            source_hash.update(block)
        if (not _current(source, source_stamp, src)
                or not _current(stage, scan_stamp, copied)):
            return None
        os.replace(stage, output)
        final_stamp = _stamp(os.fstat(copied.fileno()))
        if (final_stamp[:2] != stage_inode or not _current(output, final_stamp, copied)
                or not _current(source, source_stamp, src)):
            return None
        return {'source_path': source, 'source_stamp': source_stamp,
                'source_sha256': source_hash.hexdigest(),
                'scan_path': output, 'scan_stamp': final_stamp,
                'source_stream': facts['stream'], 'scan_stream': scan['stream'],
                'width': facts['width'], 'height': facts['height'],
                'fps': fps, 'count': count, 'trace_sha256': digest.hexdigest()}


def bind_scan(candidate):
    """Hash the unchanged scan file once, for both report and pair evidence."""
    try:
        with open(candidate['scan_path'], 'rb') as scan:
            if (not _current(candidate['scan_path'], candidate['scan_stamp'], scan)
                    or not _current(candidate['source_path'], candidate['source_stamp'])):
                return None
            digest = hashlib.sha256()
            for block in iter(lambda: scan.read(1 << 20), b''):
                digest.update(block)
            if (not _current(candidate['scan_path'], candidate['scan_stamp'], scan)
                    or not _current(candidate['source_path'], candidate['source_stamp'])):
                return None
            return dict(candidate, scan_sha256=digest.hexdigest())
    except (KeyError, OSError, TypeError):
        return None


def usable(proof, doc, selected, hdr_path=None):
    """Only an owned, live pair for these exact report and input files qualifies."""
    try:
        prov, state, facts = doc['provenance'], doc['render_state'], selected['facts']
        if (not isinstance(proof, dict) or prov.get('vfr_normalized') is not True
                or prov.get('hdr_tonemapped') is not True or prov.get('hdr_output') is not True
                or os.path.realpath(prov['input']) != proof['scan_path']
                or os.path.realpath(prov['original_input']) != proof['source_path']
                or selected['path'] != proof['scan_path']
                or selected['stamp'] != proof['scan_stamp']
                or prov.get('input_sha256') != proof['scan_sha256']
                or state['fps'] != proof['fps'] or len(state['cum']) != proof['count']
                or facts['stream'] != proof['scan_stream']
                or facts['width'] != proof['width'] or facts['height'] != proof['height']
                or hdr_path is not None and os.path.realpath(hdr_path) != proof['source_path']):
            return False
        return (_current(proof['source_path'], proof['source_stamp'])
                and _current(proof['scan_path'], proof['scan_stamp']))
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        return False
