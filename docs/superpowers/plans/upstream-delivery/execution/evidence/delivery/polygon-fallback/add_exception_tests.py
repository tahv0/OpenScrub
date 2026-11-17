from pathlib import Path
p=Path('/home/tahv0/.codex/worktrees/c832/OpenScrub/tests/test_polygon_fallback.py')
s=p.read_text()
pos=s.index('\ndef ffmpeg(')
extra='''
@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("code", [cv2.Error.StsBadArg, cv2.Error.StsOutOfRange, cv2.Error.StsAssert])
def test_geometry_raster_failure_uses_known_box(path, code, monkeypatch):
    actual = source_planes(path)
    expected = [p.copy() for p in actual]
    full_box(path, expected, (4, 4, 16, 16), "box")

    def reject_geometry(*args, **kwargs):
        raise cv2.error(code, "fillPoly", "invalid geometry", "", 0)

    monkeypatch.setattr(cv2, "fillPoly", reject_geometry)
    apply(path, actual, (4, 4, 16, 16), "box", SQUARE, (4, 4, 16, 16))
    for a, e in zip(actual, expected):
        np.testing.assert_array_equal(a, e)


@pytest.mark.parametrize("path", ["sdr", "hdr"])
@pytest.mark.parametrize("failure", [MemoryError("allocation failed"), RuntimeError("programmer failure"),
    cv2.error(cv2.Error.StsNoMem, "fillPoly", "allocation failed", "", 0)])
def test_resource_and_unrelated_failures_propagate(path, failure, monkeypatch):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cv2, "fillPoly", fail)
    with pytest.raises(type(failure)) as caught:
        apply(path, source_planes(path), (4, 4, 16, 16), "box", SQUARE, (4, 4, 16, 16))
    assert caught.value is failure

'''
p.write_text(s[:pos]+extra+s[pos:])
