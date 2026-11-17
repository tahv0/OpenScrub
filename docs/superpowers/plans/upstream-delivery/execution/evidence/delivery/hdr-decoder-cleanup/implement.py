from pathlib import Path
root = Path('/home/tahv0/.codex/worktrees/c832/OpenScrub')
p = root / 'openscrub.py'
s = p.read_text()
old = '''                if pr is enc:
                    pr.stdin.close()
            except Exception:
'''
assert s.count(old) == 1
p.write_text(s.replace(old, '''                if pr is enc:
                    pr.stdin.close()
                else:
                    pr.stdout.close()
            except Exception:
'''))
p = root / 'pyproject.toml'
s = p.read_text()
assert s.count('    "test_openscrub.py",') == 1
p.write_text(s.replace('    "test_openscrub.py",', '    "test_openscrub.py",\n    "tests/",\n    "CONTRIBUTING.md",'))
p = root / 'CONTRIBUTING.md'
s = p.read_text()
s = s.replace('python -m pytest test_openscrub.py -q      # must be green', 'python -m pytest -q                        # all discovered tests must be green')
s = s.replace('For web UI changes, also boot', 'The discovered suite includes `test_openscrub.py` and `tests/`. The HDR\ncleanup regressions use synthetic media and real FFmpeg/ffprobe with libx265;\nthey skip when those tools are unavailable. Child-reaping observations require\nPOSIX, and the injected encoder-exit case also requires `waitid`/`WNOWAIT`.\n\nFor web UI changes, also boot')
p.write_text(s)
