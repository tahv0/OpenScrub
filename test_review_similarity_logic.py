"""Fast checks for the isolated visual grouping logic (no video model needed)."""
import shutil
import subprocess

import pytest

import review_similarity_ui


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js not installed")
def test_visual_grouping_javascript_parses_and_matches_conservatively():
    # Compile the shipped browser script and exercise its matcher in Node.
    # This deliberately does not depend on Chromium, a running scan or CUDA.
    javascript = review_similarity_ui.SCRIPT + r"""
const assert = require('node:assert/strict');
const base = {i:0,bits:[0x11223344,0xa1b2c3d4],
              color:[90,100,110],edge:20,
              start:307.5,end:312,box:[200,100,340,170]};
const similar = {...base,i:1,start:308,end:309,bits:[0x11223345,0xa1b2c3d4]};
assert.equal(reviewSimilarMatch(base,similar),true);
assert.equal(reviewSimilarPopcount(0xffffffff),32);
assert.equal(reviewSimilarMatch(base,{...similar,start:370,end:371}),false);
assert.equal(reviewSimilarMatch(base,{...similar,box:[900,100,1040,170]}),false);
assert.equal(reviewSimilarMatch(base,{...similar,color:[250,250,250]}),false);
assert.equal(reviewSimilarMatch(base,{...similar,edge:0}),false);
assert.equal(reviewSimilarMatch(base,{...similar,bits:[base.bits[0]^0x7ff,base.bits[1]]}),false);
reviewSimilarReset();
assert.equal(REVIEW_SIMILAR_HASHES.size,0);
console.log('fingerprint matcher and reset ok');
"""
    run = subprocess.run([shutil.which("node"), "-e", javascript],
                         capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
    assert "matcher and reset ok" in run.stdout
