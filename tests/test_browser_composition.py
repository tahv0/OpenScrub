"""Combined editor/review ownership at actual retaining/removal boundaries."""
from test_review_save_failures import run_js


def test_retaining_panel_keeps_editor_owner_and_gesture():
    run_js("""setup();
    const cv=document.createElement('canvas');elements.set('beCv',cv);
    const slot=elements.get('beslot');slot.contains=node=>node===cv;
    let disconnected=0;
    BE.drag={kind:'move'};const gesture=BE.drag;
    BE_VIEW={cv,editor:BE,observer:{disconnect(){disconnected++}}};
    const owner=BE_VIEW;
    showPanel('boxedit_rev');
    assert.equal(BE_VIEW,owner);assert.equal(BE.drag,gesture);assert.equal(disconnected,0);
    """)


def test_successful_render_removal_releases_editor_owner():
    run_js("""setup();
    const cv=document.createElement('canvas');elements.set('beCv',cv);
    const review=elements.get('review');review.contains=node=>node===cv;
    let disconnected=0;
    BE.drag={kind:'move'};
    BE_VIEW={cv,editor:BE,observer:{disconnect(){disconnected++}}};
    const p=saveAndRender();await reply();await reply();await p;
    assert.equal(BE_VIEW,null);assert.equal(BE.drag,null);assert.equal(disconnected,1);
    """)
