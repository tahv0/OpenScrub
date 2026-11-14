"""Representative review cards show the strongest evidence while preserving group actions."""
import shutil
import subprocess

import pytest

import openscrub_web as web


def representative_script(body):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for browser script regression")
    start = "function selectReviewGroupRepresentative("
    end = "function plateVerificationBadge("
    assert start in web.APP_JS and end in web.APP_JS
    script = start + web.APP_JS.split(start, 1)[1].split(end, 1)[0]
    source = "const assert=require('node:assert/strict');\n" + script + "\n" + body
    result = subprocess.run([node, "-e", source], capture_output=True,
                            text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_strongest_plate_evidence_overrides_first_frame_and_yolo():
    representative_script(r"""
const rows=[
 {i:0,category:'plate',confidence:.95,
  plate_verification:{score:.01,decision:'suppress',applied:true}},
 {i:1,category:'plate',confidence:.42,
  plate_verification:{score:.84,decision:'retain',applied:false}},
 {i:2,category:'plate',confidence:.87,
  plate_verification:{score:.4,decision:'retain',applied:false}},
];
const result=selectReviewGroupRepresentative(rows);
assert.equal(result.row.i,1,'highest learned score, not first or highest YOLO');
assert.equal(result.reason,'highest learned plate score 84%');
assert.equal(result.row.plate_verification.decision,'retain',
             'badge must describe chosen frame, not a suppressed neighbor');
assert.equal(selectReviewGroupRepresentative(rows,rows[0]).row.i,0,
             'deliberate review sample retains its own frame');
assert.ok(selectReviewGroupRepresentative(rows,rows[0]).reason.includes('sample'));
assert.equal(selectReviewGroupRepresentative([],null),null);
assert.equal(selectReviewGroupRepresentative([{i:9,category:'face'},{i:10,category:'face'}]).row.i,9);
""")


def test_yolo_fallback_and_partial_secondary_scores():
    representative_script(r"""
const base=[
 {i:0,category:'plate',confidence:.42},
 {i:1,category:'plate',confidence:.91},
 {i:2,category:'plate',confidence:.10,plate_verification:{score:NaN}},
];
const yolo=selectReviewGroupRepresentative(base);
assert.equal(yolo.row.i,1);
assert.equal(yolo.reason,'highest YOLO confidence 91%');
const checked=base.map(x=>({...x}));
checked[0].plate_verification={score:.01};
checked[2].plate_verification={score:.78};
const result=selectReviewGroupRepresentative(checked);
assert.equal(result.row.i,2);
assert.match(result.reason,/highest learned plate score 78%/);
assert.match(result.reason,/2\/3 evaluated/);
const equal=[
 {i:0,category:'plate',confidence:.5,plate_verification:{score:.8}},
 {i:1,category:'plate',confidence:.9,plate_verification:{score:.8}},
];
assert.equal(selectReviewGroupRepresentative(equal).row.i,1,
             'YOLO may break ties between identical learned scores');
""")


def test_group_summary_updates_after_group_wide_output_changes():
    representative_script(r"""
const label={textContent:''};
const document={getElementById(id){return id==='plateGroupSummary1'?label:null}};
const TRKMEM={1:[0,1,2]};
const EN={0:false,1:true,2:false};
const OUTPUT_CHOICES={2:true};
const FINDING_META={
 0:{plate_verification:{decision:'suppress',applied:true}},
 1:{plate_verification:{decision:'retain',applied:false}},
 2:{plate_verification:{decision:'suppress',applied:true}},
};
updatePlateGroupSummary(1);
assert.match(label.textContent,/1\/3 detections hidden, 2 visible/);
assert.match(label.textContent,/1 model-filtered/);
EN[0]=true;EN[1]=true;EN[2]=true;
updatePlateGroupSummary(1);
assert.match(label.textContent,/3\/3 detections hidden, 0 visible/);
assert.ok(!label.textContent.includes('model-filtered'));
assert.match(label.textContent,/entire group/);
""")
