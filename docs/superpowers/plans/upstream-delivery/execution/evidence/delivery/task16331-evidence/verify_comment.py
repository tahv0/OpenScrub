"""Static, stdlib-only proof for Task16331; imports no product modules."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tokenize

BASE = 'a132081f1e609ed19deb4477044ee1c9b77871cc'
REL = 'openscrub_internal/render_delivery.py'
BRANCH = 'refs/heads/pr/render-recovery-comment'
OLD = ('            # Necessary leftovers remain discoverable; the report stage may\n'
       '            # still be owned by its context, so deliberately do not exit it.\n')
NEW = ('            # Close the ExitStack to discard expendable report staging; required\n'
       '            # recovery backups, final paths, and the descriptor remain discoverable.\n')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--committed', action='store_true')
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent

    def git(*argv):
        return subprocess.check_output(
            ['git', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', *argv],
            cwd=args.source)

    assert git('symbolic-ref', 'HEAD').decode().strip() == BRANCH
    before = git('show', BASE + ':' + REL)
    after = (args.source / REL).read_bytes()
    assert before.count(OLD.encode()) == 1
    assert after == before.replace(OLD.encode(), NEW.encode(), 1)
    current = git('rev-parse', 'HEAD').decode().strip()
    if args.committed:
        assert git('rev-parse', 'HEAD^').decode().strip() == BASE
        assert git('show', 'HEAD:' + REL) == after
        assert not git('status', '--porcelain=v1', '--untracked-files=all')
    else:
        assert current == BASE
        assert git('status', '--porcelain=v1', '--untracked-files=all').decode() == ' M ' + REL + '\n'

    trees = [ast.parse(data.decode('utf-8'), filename=REL, feature_version=(3, 9))
             for data in (before, after)]
    dumps = [ast.dump(tree, include_attributes=False) for tree in trees]
    assert dumps[0] == dumps[1], 'Complete AST including docstrings changed'
    tokens = [[(tok.type, tok.string) for tok in tokenize.tokenize(io.BytesIO(data).readline)
               if tok.type != tokenize.COMMENT] for data in (before, after)]
    assert tokens[0] == tokens[1], 'Non-comment token stream changed'
    raw = git('diff', '--raw', '--no-abbrev', BASE).decode().splitlines()
    assert len(raw) == 1 and raw[0].split('\t')[1] == REL
    assert raw[0].split()[0:2] == [':100644', '100644']
    assert git('diff', '--name-only', BASE).decode() == REL + '\n'
    git('diff', '--check', BASE)
    refs = git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads')
    baseline_refs = evidence / 'refs-before.txt'
    if args.committed:
        old_refs = dict(line.split() for line in baseline_refs.read_text().splitlines())
        new_refs = dict(line.split() for line in refs.decode().splitlines())
        assert old_refs.keys() == new_refs.keys()
        assert all(new_refs[key] == value for key, value in old_refs.items() if key != BRANCH)
        assert new_refs[BRANCH] == current
    else:
        baseline_refs.write_bytes(refs)

    diff = git('diff', '--no-ext-diff', '--no-textconv', BASE, '--', REL)
    (evidence / 'comment.diff').write_bytes(diff)
    result = {
        'status': 'PASS', 'base': BASE, 'head': current, 'committed': args.committed,
        'path': REL, 'base_source_sha256': digest(before),
        'changed_source_sha256': digest(after),
        'complete_ast_sha256': digest(dumps[0].encode()),
        'diff_sha256': digest(diff), 'proof_script_sha256': digest(Path(__file__).read_bytes()),
        'python39_grammar': True, 'complete_ast_equal_including_docstrings': True,
        'noncomment_tokens_equal': True, 'exact_two_comment_line_replacement': True,
        'only_changed_file': REL, 'mode_unchanged': '100644', 'diff_check': 'PASS',
        'other_branch_refs_preserved': True if args.committed else 'baseline captured',
        'product_imports_or_runtime_tests': False,
    }
    filename = 'proof-committed.json' if args.committed else 'proof-precommit.json'
    (evidence / filename).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
