"""Real emitted page with controlled paused API responses while integration lands."""
from test_editor_resize import launch_editor_page


def test_paused_review_and_resume_editor(tmp_path):
    launch_editor_page(tmp_path,'checkpoint_paused_browser.cjs',restart=False)
