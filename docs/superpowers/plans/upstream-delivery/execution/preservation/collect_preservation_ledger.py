#!/usr/bin/env python3
"""Rebuild metadata/path/hunk inventory. This is NOT an automated source audit.

Run from repository root. Only writes adjacent audit CSV/JSON artifacts.
Hand-reviewed evidence records below apply to named hunks, never entire commits.
"""
import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

BASE = "5d3a15ae683c08f368d6ba4bd0d2d77b4e7b8e2f"
DONOR = "b4d0c75f25d91510fe1692f901d11853dc7db005"
OUT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", *args], text=True)


# family, disposition, evidence, exact evidence scope. Source inspection does
# not mean the whole commit was inspected, nor that a failure was reproduced.
REVIEWED = {
    "8697c28": ("mask-render-fidelity", "investigate", "source-inspected-subset", "N02/N03: HDR chroma projection and invalid-polygon fallback; compound-hole feature kept separate"),
    "ccff62f": ("late-window-dense-smoothing", "investigate", "source-isolated-probe", "N01: real function AST plus fake decoder: upstream 17873 reads vs donor 1 with simulated successful seek; failure fallback 17873; no real video timing"),
    "a6419cc": ("O05-lettering-only", "downstream", "source-inspected-subset", "np.bincount component coverage; already explicitly mapped O05, not new omission"),
    "1fe4e34": ("O05-lettering-only", "downstream", "hunk-inventory", "Optional lettering-only implementation; O05 already covers donor; no behavior verification"),
    "39b4ed8": ("P02-explicit-output", "PR", "hunk-inventory", "Existing P02 donor, individual implementation not reverified here"),
    "2900930": ("P01-save-as", "PR", "hunk-inventory", "Existing P01 donor; first PR also requires new byte-progress feedback"),
    "539432c": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16; preserve per-bug reproduction gate"),
    "a056dff": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16; preserve current upstream close-up face margins"),
    "c79cb29": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16"),
    "4a6675f": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16"),
    "e15c5eb": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16"),
    "98c3231": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16"),
    "77755f0": ("P16-review-render-fidelity", "PR", "hunk-inventory", "Already mapped P16"),
    "3e92c90": ("P07-save-state", "PR", "source-inspected-subset", "Captured job/view fencing and delayed failed-save handling; training hooks excluded"),
    "5e96740": ("P05-P07-preview-save", "PR", "source-inspected-subset", "Atomic JPEG producer plus frozen HTTP bytes; pending-review versions/job-switch guard; already mapped"),
    "90e67b6": ("P05-P07-preview-save-merge", "PR", "source-inspected-subset", "First-parent delta reconciled against 5e96740: JPEG publication and save state, not whole-workbench transplant"),
    "4fd88af": ("P06-P07-large-save-merge", "PR", "source-inspected-subset", "First-parent delta: no-op save guard, timings, bounded compact writer, sparse browser delta; manual additions not idempotent by this guard"),
    "d9a96c3": ("P06-P07-large-save", "PR", "source-inspected-subset", "Constituent delta verified via owning 4fd88af first-parent merge; sparse/no-op/timing helpers do not establish current upstream speedup"),
    "08f432b": ("P03-polling-mixed-sections", "PR", "source-inspected-subset", "Bounded log cursor, activity, preview publication; section/learning paths excluded; already mapped"),
    "db9a142": ("training-mixed-render-review", "investigate", "source-inspected-subset", "Worker preserves/rolls back review document around render; separate training invalid-output guard; N06"),
    "aaeb71a": ("findings-library-mixed-runtime", "investigate", "source-inspected-subset", "Vault guard/cache locking/tracker and lifecycle hooks mixed into Findings introduction; investigate generic scope"),
    "7e5c7b4": ("P02-P16-overlay-semantics", "investigate", "source-inspected-subset", "N04: detector proposal versus effective Blur/Keep overlay legend/color subset; learned badges excluded"),
    "eedef89": ("P17-geometry-disclosure-mixed-checker", "investigate", "source-inspected-subset", "N05: plain Detector wording and no-perspective-tracking disclosure survive checker removal; score UI removed"),
    "6d5e8fd": ("vault-cache-lifecycle", "removed-system-only", "source-inspected-subset", "Only adds reader lease around journal overlay and clears journal caches; carry lifecycle requirement to P08/P10, not journal code"),
    "496e017": ("P10-exact-crop-colors", "PR", "source-inspected-subset", "format=rgb24 before source-space crop; P10 follow-up, not standalone proof of upstream crop bug"),
    "217f323": ("P06-P07-allowlist-compatibility", "removed-system-only", "source-inspected-subset", "Journal fast-save repairs preexisting suggest_allowlist behavior; preserve existing upstream contract in P06/P07"),
    "9753212": ("P13-build-context", "PR", "source-inspected-subset", "Recursive cache/environment/media/weights exclusions; .dockerignore already named P13"),
    "7bc2336": ("P14-windows-context", "PR", "source-inspected-subset", "Active daemon context and docker-driver builder selection; remove training/dependency-image machinery"),
    "2704018": ("P14-windows-context-tests", "PR", "source-inspected-subset", "Textual helper assertions; not actual Windows or GPU evidence"),
    "da50a6e": ("cuda-audit-only-helper", "removed-system-only", "path-inventory", "Output-directory fix belongs to excluded CUDA audit architecture; no existing upstream target helper"),
    "96a3a50": ("training-compose-only", "removed-system-only", "path-inventory", "Training overlay inclusion; excluded from inference-only P14"),
    "d6e9efc": ("privacy-normalization", "already upstream", "source-compared", "Current Austin normalizes dash AND slash across adaptive OCR/transcripts; retain upstream a0b50a5"),
    "c874ade": ("privacy-normalization", "already upstream", "source-compared", "Repairs initial donor Unicode regex; upstream authoritative broader normalization retained"),
    "0610cd5": ("privacy-localized-motion", "already upstream", "source-compared", "Current Austin text_scan_stride localized-change implementation authoritative; donor older helper excluded"),
    "ea73eef": ("PhiMemory-throughput", "already upstream", "source-compared", "Austin has length buckets plus compiled rapidfuzz batch; donor Python loop is regression"),
    "212da9b": ("PhiMemory-order", "already upstream", "source-compared", "Austin batch matching preserves insertion serial; retain upstream"),
    "a11a392": ("removed-preview-capture-cache", "removed-system-only", "path-inventory", "finding_previews.py only; P11 investigates independent upstream costs, not restoring cache"),
}


def family(subject, paths):
    s = (subject + " " + " ".join(paths)).lower()
    rules = [
        (r"docker|cuda|buildx|compose|powershell", "container-windows-build"),
        (r"ocr.*(dash|privacy|localized)|unicode regex|text promptly", "privacy-ocr"),
        (r"ocr memory|indexed ocr|insertion order", "PhiMemory"),
        (r"plate.text|known.plate|ocr search", "O03-plate-search"),
        (r"narrow|lettering", "O05-lettering-only"),
        (r"stop.review|checkpoint|resumable|resume", "P18-checkpoint"),
        (r"polling|job.progress|activity|eta|throughput in job|progressively slower", "P03-P04-progress"),
        (r"logging|runtime.errors|crash|diagnostic|heartbeat", "P12-diagnostics"),
        (r"vault|encryption|job deletion|image leases", "cache-vault-lifecycle-candidate"),
        (r"needs review|partially reviewed", "P15-view-filter-candidate"),
        (r"plate editor|marquee", "P17-quad-candidate"),
        (r"track representatives|legacy listing|detections get|/detections|legacy.*rebuild", "P08-cache-index-candidate"),
        (r"embedded js|embedded.*regex|draft download", "embedded-script-compatibility"),
        (r"exact frame inspection|borrowed review", "P10-source-frame-candidate"),
        (r"training|learned.model|learning|held.out|proposal.box|secondary.model|plate.verifier", "custom-training-verifier"),
        (r"journal|sqlite|materializ|fast.ack|full.report.*publish|rebound.*confirmation", "removed-review-journal"),
        (r"section", "removed-video-sections"),
        (r"redraw|off.frame|reanchor|anchor.repair|source.repair", "removed-offframe-repair"),
        (r"409|confirmation|confirm.*preview|archive.conflict|source.rebind|reconfirm|stale.*(image|picture|jpeg|preview)", "removed-confirmation-recovery"),
        (r"similarity|visually similar", "removed-similarity-workbench"),
        (r"filter|sampling|sample ten|sample grouped", "P15-view-filter-candidate"),
        (r"prefetch|viewport|visible.*thumbnail|pag(e|in).*card|preview.throughput", "P09-thumbnail-scheduling"),
        (r"index|report.read|cache.*report|revision.*listing|listing.*revision|reconcil", "P08-cache-index-candidate"),
        (r"decode|preview|crop|cached.picture|jpeg", "P08-P10-preview-candidate"),
        (r"corner|quad|polygon|rotation|rotate", "P17-quad-candidate"),
        (r"save|choice|decision|explicit.*review", "P02-P06-P07-save-candidate"),
        (r"mask|silhouette|coverage|shaped|frame.identity", "P16-mask-candidate"),
        (r"findings|gallery|human.example", "removed-findings-library"),
        (r"package|distribution|sdist|wheel", "packaging-owning-feature"),
        (r"smoke|integration|release|workflow|syntax|test|regression|ci", "validation-integration-support"),
    ]
    for pattern, result in rules:
        if re.search(pattern, s):
            return result
    return "unresolved-history"


def kind(path):
    if path.startswith("test_") or path.startswith("tests/"):
        return "test"
    if path.startswith("docs/") or path.endswith(".md"):
        return "documentation"
    if path.startswith(".github/"):
        return "ci"
    if path.startswith("benchmark/") or path.startswith("tools/"):
        return "developer-tool"
    return "production-build-config"


def main():
    rows = []
    for line in git("log", "--reverse", "--format=%H%x09%P%x09%s", BASE + ".." + DONOR).splitlines():
        sha, parents, subject = line.split("\t", 2)
        parent = parents.split()[0]
        paths = git("diff", "--name-only", parent, sha).splitlines()
        patch = git("diff", "--unified=0", parent, sha)
        # Retain changed-function headers as a navigation aid only.
        scopes = sorted(set(re.sub(r"^@@.*?@@\s*", "", ln) for ln in patch.splitlines() if ln.startswith("@@")))
        reviewed = REVIEWED.get(sha[:7])
        if reviewed:
            fam, disposition, evidence, note = reviewed
        else:
            fam = family(subject, paths)
            disposition, evidence = "investigate", "metadata-path-hunk-inventory"
            note = "Provisional family from subject/path/hunk inventory; semantic source review pending"
        rows.append(dict(sha=sha, parents=parents, merge=len(parents.split()) > 1,
                         subject=subject, family=fam, disposition=disposition,
                         evidence=evidence, note=note,
                         paths=";".join(paths),
                         production_paths=";".join(p for p in paths if kind(p) == "production-build-config"),
                         changed_scopes=";".join(scopes),
                         diff_basis="first-parent"))
    with (OUT / "preservation-commits.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    changed = git("diff", "--name-status", BASE, DONOR).splitlines()
    paths = [dict(status=line.split("\t")[0], path=line.split("\t")[-1], kind=kind(line.split("\t")[-1])) for line in changed]
    with (OUT / "preservation-paths.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["status", "path", "kind"])
        writer.writeheader()
        writer.writerows(paths)
    counts = dict(base=BASE, donor=DONOR, commits=len(rows),
                  merge_commits=sum(row["merge"] for row in rows),
                  non_merge_commits=sum(not row["merge"] for row in rows),
                  changed_paths=len(paths),
                  dispositions=dict(Counter(row["disposition"] for row in rows)),
                  evidence=dict(Counter(row["evidence"] for row in rows)),
                  families=dict(Counter(row["family"] for row in rows)),
                  paths_by_kind=dict(Counter(row["kind"] for row in paths)),
                  semantic_audit_complete=False,
                  scale_baselines_complete=False)
    (OUT / "preservation-counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
