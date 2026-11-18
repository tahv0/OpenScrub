"""Verify Task 116 without importing or executing product code."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tokenize

BASE = "17dfe5d575306dea395b680205038e606ad598a2"
BRANCH = "refs/heads/pr/scan-sanity-test-comment"
SOURCE = "tests/test_first_scan_sanity.py"
OLD = b"    # All Detection fields and report-only choices are pinned, including order."
NEW = b"    # Detection fields, report-only values, and Detection list order are pinned."
DUMP_OPTIONS = {"annotate_fields": True, "include_attributes": False, "indent": None}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--committed", action="store_true")
    args = parser.parse_args()
    repo = args.repository.resolve()

    def git(*argv):
        return subprocess.check_output(
            ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *argv],
            cwd=repo,
        )

    head = git("rev-parse", "HEAD").decode().strip()
    assert git("symbolic-ref", "HEAD").decode().strip() == BRANCH
    base = git("show", BASE + ":" + SOURCE)
    current = (repo / SOURCE).read_bytes()
    assert base.count(OLD) == 1
    assert current == base.replace(OLD, NEW, 1), "Unexpected source byte changes"
    metadata = (repo / SOURCE).lstat()
    assert stat.S_ISREG(metadata.st_mode)
    base_mode = git("ls-tree", BASE, "--", SOURCE).decode().split()[0]
    assert base_mode == "100644" and stat.S_IMODE(metadata.st_mode) == 0o644
    git("diff", "--check", BASE)
    if args.committed:
        assert git("rev-parse", "HEAD^").decode().strip() == BASE
        assert git("show", "HEAD:" + SOURCE) == current
        assert git("status", "--porcelain=v1") == b"", "Worktree must be clean"
        assert git("ls-tree", "HEAD", "--", SOURCE).decode().split()[0] == base_mode
        changed = git("diff", "--name-status", "--no-renames", BASE, "HEAD")
        diff = git("diff", "--no-ext-diff", "--no-renames", BASE, "HEAD", "--", SOURCE)
        git("diff", "--check", BASE, "HEAD")
    else:
        assert head == BASE
        assert git("diff", "--cached", "--name-only") == b""
        assert git("ls-files", "--others", "--exclude-standard") == b""
        changed = git("diff", "--name-status", "--no-renames", BASE)
        diff = git("diff", "--no-ext-diff", "--no-renames", BASE, "--", SOURCE)
    assert changed == ("M\t" + SOURCE + "\n").encode()
    delta = [line for line in diff.splitlines()
             if line[:1] in (b"+", b"-") and not line.startswith((b"+++", b"---"))]
    assert delta == [b"-" + OLD, b"+" + NEW], "Not the exact comment-only diff"

    def parsed(data, grammar=None):
        options = {"type_comments": True}
        if grammar is not None:
            options["feature_version"] = grammar
        return ast.parse(data.decode("utf-8"), filename=SOURCE, **options)

    before_ast = ast.dump(parsed(base), **DUMP_OPTIONS)
    after_ast = ast.dump(parsed(current), **DUMP_OPTIONS)
    assert before_ast == after_ast, "AST/docstring change"
    before39 = ast.dump(parsed(base, (3, 9)), **DUMP_OPTIONS)
    after39 = ast.dump(parsed(current, (3, 9)), **DUMP_OPTIONS)
    assert before39 == after39

    def noncomment_tokens(data):
        return [(item.type, item.string)
                for item in tokenize.tokenize(io.BytesIO(data).readline)
                if item.type != tokenize.COMMENT]

    before_tokens = noncomment_tokens(base)
    after_tokens = noncomment_tokens(current)
    assert before_tokens == after_tokens, "Non-comment token change"
    refs = git("for-each-ref", "--format=%(refname) %(objectname)")
    evidence = Path(__file__).resolve().parent
    refs_before = (evidence / "refs-before.txt").read_bytes()
    if args.committed:
        expected_refs = refs_before.replace(
            (BRANCH + " " + BASE + "\n").encode(),
            (BRANCH + " " + head + "\n").encode(),
            1,
        )
        assert refs == expected_refs, "A different ref changed"
    else:
        assert refs == refs_before
    print(json.dumps({
        "status": "PASS", "base": BASE, "head": head,
        "phase": "committed" if args.committed else "precommit",
        "path": SOURCE, "mode": base_mode,
        "base_blob": git("rev-parse", BASE + ":" + SOURCE).decode().strip(),
        "source_before_sha256": sha(base), "source_after_sha256": sha(current),
        "source_before_bytes": len(base), "source_after_bytes": len(current),
        "interpreter": {"executable": sys.executable, "version": sys.version},
        "ast_parse_options": {"type_comments": True},
        "ast_dump_options": DUMP_OPTIONS,
        "ast_before_sha256": sha(before_ast.encode()),
        "ast_after_sha256": sha(after_ast.encode()),
        "ast_hash_scope": "Interpreter-version-specific ast.dump; not a cross-version digest",
        "complete_ast_including_docstrings_equal": True,
        "python39_grammar": {"feature_version": [3, 9], "both_parse": True,
                             "ast_equal": True, "actual_python39_runtime": False},
        "noncomment_token_comparison": "Exact (type, string) sequence; positions omitted",
        "noncomment_token_count": len(before_tokens), "noncomment_tokens_equal": True,
        "one_file_exact_comment_replacement": True, "diff_check": "PASS",
        "other_refs_preserved": True,
        "committed_source_equals_working_file": args.committed,
        "clean_worktree": args.committed,
        "old_comment": OLD.decode(), "new_comment": NEW.decode(),
    }, indent=2))


if __name__ == "__main__":
    main()
