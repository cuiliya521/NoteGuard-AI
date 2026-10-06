"""Evaluate NoteGuard V5 on a frozen labelled dataset.

Modes:
- rule-only: deterministic local rules only; no API key or external calls.
- full: rule + DeepSeek semantic review + V5 arbitration. One semantic call per case.

This script evaluates classification only. It deliberately does NOT generate rewrite drafts,
so a full 80-case run uses 80 semantic-review calls rather than additional draft calls.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from services.rule_checker import check_text, load_rules
from services.workflow_ai_v2 import review_semantics
from services.workflow_v2 import arbitrate_rule_findings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "eval" / "final_v5_80.json"
RULES_PATH = ROOT / "data" / "rules.json"


def _metrics(tp: int, tn: int, fp: int, fn: int) -> dict[str, float | int]:
    total = tp + tn + fp + fn
    return {
        "total": total,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": (tp + tn) / total if total else 0.0,
        "risk_recall": tp / (tp + fn) if tp + fn else 0.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "false_negative_rate": fn / (tp + fn) if tp + fn else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def evaluate(dataset_path: Path, mode: str) -> dict:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    rules = load_rules(RULES_PATH)
    results = []
    semantic_unavailable = 0

    for case in payload["cases"]:
        title = case.get("title", "")
        body = case.get("body", "")
        raw_findings = tuple(check_text(title, body, rules))

        if mode == "full":
            semantic = review_semantics(title, body)
            if not semantic.available:
                semantic_unavailable += 1
            findings = arbitrate_rule_findings(raw_findings, semantic)
            predicted_risk = bool(findings or semantic.issues)
            semantic_issue_count = len(semantic.issues)
            semantic_error = semantic.error
        else:
            findings = raw_findings
            predicted_risk = bool(findings)
            semantic_issue_count = 0
            semantic_error = ""

        gold_risk = case["gold_label"] == "risk"
        outcome = (
            "TP" if gold_risk and predicted_risk else
            "TN" if not gold_risk and not predicted_risk else
            "FP" if not gold_risk and predicted_risk else
            "FN"
        )
        results.append({
            "id": case["id"],
            "scenario": case["scenario"],
            "gold_label": case["gold_label"],
            "gold_type": case["gold_type"],
            "predicted_label": "risk" if predicted_risk else "safe",
            "outcome": outcome,
            "raw_rule_terms": [item.term for item in raw_findings],
            "arbitrated_rule_terms": [item.term for item in findings],
            "semantic_issue_count": semantic_issue_count,
            "semantic_error": semantic_error,
        })

    counts = Counter(item["outcome"] for item in results)
    metrics = _metrics(counts["TP"], counts["TN"], counts["FP"], counts["FN"])
    error_types = Counter(
        item["gold_type"] for item in results if item["outcome"] in {"FP", "FN"}
    )
    scenario_errors = Counter(
        item["scenario"] for item in results if item["outcome"] in {"FP", "FN"}
    )
    return {
        "dataset": payload.get("name"),
        "dataset_version": payload.get("version"),
        "mode": mode,
        "semantic_unavailable_cases": semantic_unavailable,
        "metrics": metrics,
        "error_type_breakdown": dict(error_types),
        "scenario_error_breakdown": dict(scenario_errors),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mode", choices=("rule-only", "full"), default="rule-only")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate(args.dataset, args.mode)
    m = report["metrics"]
    print(f"dataset={report['dataset']} mode={report['mode']}")
    print(
        "TP={tp} TN={tn} FP={fp} FN={fn} "
        "accuracy={accuracy:.3f} recall={risk_recall:.3f} "
        "precision={precision:.3f} FNR={false_negative_rate:.3f} FPR={false_positive_rate:.3f}".format(**m)
    )
    if args.mode == "full":
        print(f"semantic_unavailable_cases={report['semantic_unavailable_cases']}")
        if report["semantic_unavailable_cases"]:
            raise SystemExit(
                "Full evaluation is invalid because semantic review was unavailable for one or more cases."
            )

    errors = [r for r in report["results"] if r["outcome"] in {"FP", "FN"}]
    print("errors=" + ",".join(f"{r['id']}:{r['outcome']}" for r in errors))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved={args.output}")


if __name__ == "__main__":
    main()
