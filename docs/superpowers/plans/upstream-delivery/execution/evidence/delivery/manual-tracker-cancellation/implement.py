from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/openscrub.py')
s=p.read_text(); start=s.index('def track_manual_region('); end=s.index('\ndef group_persons(',start)
a=s[start:end]
a=a.replace('    log = (cb.log if cb else print)\n    cap =', '''    log = (cb.log if cb else print)

    def _check_cancelled():
        if cb is not None and cb.cancelled():
            raise PipelineCancelled()

    # Cancellation takes precedence even when the input is unusable.
    _check_cancelled()
    cap =''',1)
a=a.replace('            except Exception as e:', '            except PipelineCancelled:\n                raise\n            except Exception as e:',1)
a=a.replace('                ps = []\n            if ps:', '                ps = []\n            _check_cancelled()\n            if ps:',1)
a=a.replace('                out.append((t2, (cur[0]', '                _check_cancelled()\n                out.append((t2, (cur[0]',1)
a=a.replace('        vit = _vittrack_factory(log)\n', '        vit = _vittrack_factory(log)\n        _check_cancelled()\n',1)
a=a.replace('            samples.sort(key=lambda s: s[0])', '            _check_cancelled()\n            samples.sort(key=lambda s: s[0])',1)
# NCC loop only; retain the existing Vit loop check verbatim.
a=a.replace('            while True:\n                t2 = t + direction * step', '            while True:\n                _check_cancelled()\n                t2 = t + direction * step',1)
a=a.replace('        samples.sort(key=lambda s: s[0])\n        return samples', '        _check_cancelled()\n        samples.sort(key=lambda s: s[0])\n        return samples',1)
p.write_text(s[:start]+a+s[end:])
