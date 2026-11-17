from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_hdr_chroma_coverage.py')
s=p.read_text()
a=s.index('    # Odd source values')
b=s.index('\n\n\n@pytest.mark.parametrize',a)
s=s[:a]+'''    # Odd source values make inpaint's multiples of four distinguishable.
    # Seeded spatial contrast avoids mosaic's checkerboard sampling aliases.
    rng = np.random.default_rng(161)
    return [(rng.integers(0, 256, (size, size), dtype=np.uint16) * 4 + 1)
            for size in (32, 16, 16)]'''+s[b:]
p.write_text(s)
