"""Opt-in real editor/Chromium and stock Tesseract integration."""
from test_editor_resize import launch_editor_page


def test_plate_search_editor_page(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENSCRUB_PLATE_BROWSER_FIXTURE','1')
    launch_editor_page(tmp_path,'plate_search_browser.cjs',restart=False)


def test_plate_suggestion_track_editor_page(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENSCRUB_PLATE_BROWSER_FIXTURE','1')
    launch_editor_page(tmp_path,'plate_search_track_browser.cjs',restart=False)
