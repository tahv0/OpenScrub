from test_editor_resize import launch_editor_page

def test_actual_paused_backend_page(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENSCRUB_REAL_CHECKPOINT_PAGE','1')
    launch_editor_page(tmp_path,'checkpoint_actual_browser.cjs',restart=False)
