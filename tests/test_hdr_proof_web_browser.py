"""Opt-in Chromium check of Scan Setup HDR proof admission."""
from test_editor_resize import launch_editor_page


def test_hdr_plate_proof_scan_setup_and_real_admission(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENSCRUB_HDR_PROOF_WEB_FIXTURE','1')
    launch_editor_page(tmp_path,'hdr_proof_web_browser.cjs',restart=False)
