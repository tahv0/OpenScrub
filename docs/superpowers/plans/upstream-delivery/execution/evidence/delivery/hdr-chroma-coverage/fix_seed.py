from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_hdr_chroma_coverage.py')
s=p.read_text().replace('np.random.default_rng(161)', 'np.random.default_rng(162)')
p.write_text(s)
