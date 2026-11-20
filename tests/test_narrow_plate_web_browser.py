"""Opt-in Chromium check of real Scan Setup multipart admission."""
from test_editor_resize import launch_editor_page


def test_lettering_scan_setup_and_real_admission(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENSCRUB_LETTERING_WEB_FIXTURE','1')
    launch_editor_page(tmp_path,'narrow_plate_web_browser.cjs',restart=False)
