#!/usr/bin/env python3
"""Score a retrieval run against docs/eval/retrieval-eval-set.json.

Usage:
    python3 docs/eval/score.py predictions.json
    python3 docs/eval/score.py --selftest

predictions.json maps question id -> either a list of retrieved target ids, or
{"targets": [...], "gap_reported": bool}. Target ids use the grammar documented
in docs/eval/README.md; `*` globs (so `hero:*` matches any hero).
"""
import json
import os
import sys
from fnmatch import fnmatch

SET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retrieval-eval-set.json")


def _hit(target, retrieved):
    """A must/may target is hit if any retrieved id matches it (target may glob)."""
    return any(fnmatch(r, target) for r in retrieved)


def _allowed(retrieved_id, allowed):
    return any(fnmatch(retrieved_id, a) for a in allowed)


def score(questions, predictions):
    per_q, gap_qs, gap_hits = [], 0, 0
    for q in questions:
        pred = predictions.get(q["id"], [])
        if isinstance(pred, dict):
            retrieved, gap_reported = pred.get("targets", []), bool(pred.get("gap_reported"))
        else:
            retrieved, gap_reported = pred, False

        must = q["must"]
        recall = sum(_hit(t, retrieved) for t in must) / len(must)
        allowed = must + q["may"]
        noise = (sum(not _allowed(r, allowed) for r in retrieved) / len(retrieved)) if retrieved else 0.0
        per_q.append({"id": q["id"], "class": q["class"], "recall": recall, "noise": noise})

        if q["prose_gap"]:
            gap_qs += 1
            gap_hits += gap_reported

    n = len(per_q)
    return {
        "questions": n,
        "must_recall": sum(r["recall"] for r in per_q) / n,
        "exact_rate": sum(r["recall"] == 1.0 for r in per_q) / n,
        "noise_rate": sum(r["noise"] for r in per_q) / n,
        "gap_detection": (gap_hits / gap_qs) if gap_qs else None,
        "per_question": per_q,
    }


def _selftest():
    qs = [
        {"id": "a", "class": "x", "must": ["hero:1", "item:2"], "may": ["hero:*"], "prose_gap": False},
        {"id": "b", "class": "x", "must": ["prose:lane-phase"], "may": [], "prose_gap": True},
    ]
    # perfect run, gap reported
    r = score(qs, {"a": ["hero:1", "item:2"], "b": {"targets": ["prose:lane-phase"], "gap_reported": True}})
    assert r["must_recall"] == 1.0 and r["exact_rate"] == 1.0 and r["noise_rate"] == 0.0
    assert r["gap_detection"] == 1.0
    # half recall on a, noise from an out-of-set id, gap missed
    r = score(qs, {"a": ["hero:1", "analytics:hero-stats"], "b": []})
    assert r["must_recall"] == 0.25, r["must_recall"]          # (0.5 + 0.0) / 2
    assert r["exact_rate"] == 0.0
    assert r["noise_rate"] == 0.25, r["noise_rate"]            # (1/2 + 0) / 2
    assert r["gap_detection"] == 0.0
    # `may` absorbs an extra hero without counting as noise
    r = score(qs, {"a": ["hero:1", "item:2", "hero:99"], "b": ["prose:lane-phase"]})
    assert r["noise_rate"] == 0.0
    # empty prediction is zero recall, not a crash or a divide-by-zero
    assert score(qs, {})["must_recall"] == 0.0
    print("selftest ok")


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    if argv[1] == "--selftest":
        return _selftest()
    questions = json.load(open(SET_PATH))["questions"]
    result = score(questions, json.load(open(argv[1])))
    per_q = result.pop("per_question")
    print(json.dumps(result, indent=2))
    for r in sorted(per_q, key=lambda r: r["recall"]):
        if r["recall"] < 1.0:
            print(f"  miss {r['id']:<12} recall={r['recall']:.2f} noise={r['noise']:.2f}")


if __name__ == "__main__":
    main(sys.argv)
