from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_manual_tracker_cancel.py')
s=p.read_text().replace("value['done']", "value['state'] == 'done'")
s=s.replace("        return self.trace\n\n    def hooks", "        if (self.trigger == 'vit_final_break' and event == 'line'\n                and frame.f_code is engine.track_manual_region.__code__\n                and frame.f_lineno == VIT_BREAK and frame.f_locals.get('direction') == -1):\n            self.mark_cancel()\n        return self.trace\n\n    def hooks")
s=s.replace('HOLD_ADVANCE = HOLD_APPEND + 1','HOLD_ADVANCE = HOLD_APPEND + 1\nVIT_BREAK = next(SOURCE_START + i + 1 for i, line in enumerate(SOURCE_LINES)\n                 if "if t2 < t0 - 1e-6 or t2 > t1 + 1e-6:" in line)')
s=s.replace("def test_vit_final_return_observes_cancellation_from_last_update(media):\n    probe = Probe()", "def test_vit_final_return_observes_cancellation_after_last_loop_check(media):\n    probe = Probe(trigger='vit_final_break')")
s=s.replace("            if len(updates) == 14:\n                probe.mark_cancel()\n",'')
p.write_text(s)
