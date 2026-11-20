"""Real Scan Setup and Stop control against a synthetic native MP4."""
from test_editor_resize import launch_editor_page


def test_checkpoint_setup_and_stop_real_page(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENSCRUB_CHECKPOINT_BROWSER_FIXTURE', '1')
    launch_editor_page(tmp_path, 'checkpoint_setup_browser.cjs', restart=False)
