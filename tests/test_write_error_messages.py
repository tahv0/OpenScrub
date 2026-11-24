"""A failed WRITE of the output (I/O error, read-only, permission, full disk)
is named as a disk/folder problem with steps — never as an encoder problem."""
import errno
import tempfile

import openscrub
import openscrub_web as web

FFMPEG_EIO = (b"[mp4 @ 0x1] av_interleaved_write_frame(): Input/output error\n"
              b"    Last message repeated 1 times\n"
              b"[out#0/mp4 @ 0x2] Error writing trailer of /data/jobs/x/.render-1.tmp.mp4: "
              b"Input/output error\n")


def _failure(stderr, hint="if it persists, try the x264 encoder"):
    f = tempfile.TemporaryFile()
    f.write(stderr)
    return openscrub._ffmpeg_failure(f, "video encode", 1, hint)


def test_engine_names_a_write_failure_not_the_encoder():
    msg = str(_failure(FFMPEG_EIO))
    assert "x264" not in msg
    assert "writing the output file failed" in msg
    assert "Input/output error" in msg                 # ffmpeg's own words kept


def test_engine_keeps_the_encoder_hint_for_encoder_failures():
    msg = str(_failure(b"[h264_nvenc @ 0x1] OpenEncodeSessionEx failed: out of memory\n"))
    assert "try the x264 encoder" in msg


def test_web_explains_a_write_error_with_steps():
    msg = web._with_disk_full_hint(str(_failure(FFMPEG_EIO)), RuntimeError(), "render")
    assert "could not be written to disk" in msg
    assert "free space" in msg and "antivirus" in msg and "connected" in msg
    assert "Retry render" in msg and "review choices are kept" in msg


def test_web_explains_os_level_write_errors():
    for code, words in ((errno.EIO, "Input/output error"), (errno.EROFS, "Read-only file system"),
                        (errno.EACCES, "Permission denied")):
        msg = web._with_disk_full_hint("cannot open the video", OSError(code, words), "scan")
        assert "could not be read or written on disk" in msg and "Retry scan" in msg, code
        assert "antivirus" in msg


def test_full_disk_message_is_unchanged():
    msg = web._with_disk_full_hint("No space left on device", OSError(errno.ENOSPC, "x"), "render")
    assert "the disk is full" in msg and "Retry render" in msg


def test_unrelated_errors_get_no_hint():
    assert web._with_disk_full_hint("synthetic failure", RuntimeError(), "render") == "synthetic failure"
