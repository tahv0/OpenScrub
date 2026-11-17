from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_large_report_io.py')
s=p.read_text().replace('legacy stream_writes key counts encoder chunks','encoder_chunks counts encoder pieces').replace('stream_writes','encoder_chunks')
p.write_text(s)
