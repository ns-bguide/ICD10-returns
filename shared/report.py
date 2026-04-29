"""Standardized evaluation report for ICD-10-CM entity strategies.

Runs ALL validation layers on an entity and produces a single consistent
report. Both strategy instances MUST use this script for final reporting.

Validation layers:
  1. COVERAGE: % of 86,827 official ICD-10-CM titles matched
  2. DEV FP: Static hand-crafted FP dataset (fp_dataset.json) — 171 FP, 600 TP
  3. STATIC VALIDATION: Static generated FP dataset (fp_validation.json) — 657 FP, 300 TP
  4. ADVERSARIAL: Dynamically generated from entity's own vocabulary — can't be memorized
  5. ENTITY SIZE: File size, entries, patterns

Usage:
    python3 ../shared/report.py entity.xml
    python3 ../shared/report.py entity.xml --output report.json
"""

import argparse
import json
import sys
from pathlib import Path

SHARED_DIR = Path(__file__).parent

# Import sibling modules
sys.path.insert(0, str(SHARED_DIR))
from evaluate import load_entity_entries, evaluate_coverage, evaluate_fp, evaluate_validation
from adversarial_validation import run_adversarial_validation


def run_full_report(xml_path: str, adversarial_seed: int = 42) -> dict:
    print(f"Loading entity: {xml_path}")
    flat_entries, regex_patterns, entity_stats = load_entity_entries(xml_path)
    print(f"  {len(flat_entries)} flat entries, {len(regex_patterns)} regex patterns\n")

    print("1/4  Coverage against ICD-10-CM titles...")
    coverage = evaluate_coverage(xml_path, flat_entries, regex_patterns)

    print("2/4  Development FP dataset...")
    fp_dev = evaluate_fp(flat_entries, regex_patterns)

    print("3/4  Static validation dataset...")
    fp_val = evaluate_validation(flat_entries, regex_patterns)

    print("4/4  Adversarial validation (dynamic, seed={})...".format(adversarial_seed))
    adversarial = run_adversarial_validation(xml_path, seed=adversarial_seed)

    return {
        "entity_path": str(xml_path),
        "entity_stats": entity_stats,
        "coverage": coverage,
        "dev_fp": fp_dev,
        "static_validation": fp_val,
        "adversarial": adversarial,
    }


def print_report(r: dict):
    es = r["entity_stats"]
    cov = r["coverage"]
    dev = r["dev_fp"]["summary"]
    val = r.get("static_validation", {}).get("summary", {})
    adv = r["adversarial"]["summary"]

    w = 70
    print()
    print("=" * w)
    print("ICD-10-CM ENTITY — STANDARDIZED EVALUATION REPORT")
    print("=" * w)
    print(f"  Entity: {r['entity_path']}")

    # ── Size
    print(f"\n{'─── ENTITY SIZE ':─<{w}}")
    print(f"  File size:          {es['file_size_kb']:>10.1f} KB")
    print(f"  Entities:           {es['total_entities']:>10d}  ({es['public_entities']} public, {es['private_entities']} private)")
    print(f"  Flat entries:       {es['flat_entries']:>10,}")
    print(f"  Active patterns:    {es['active_patterns']:>10,}")
    print(f"  Ref patterns:       {es['reference_patterns']:>10,}")
    print(f"  Score=0 (FP block): {es['score0_patterns']:>10,}")

    # ── Coverage
    print(f"\n{'─── COVERAGE ':─<{w}}")
    print(f"  Official titles:    {cov['total_titles']:>10,}")
    print(f"  Covered:            {cov['covered']:>10,}  ({cov['coverage_pct']}%)")
    print(f"  Uncovered:          {cov['uncovered']:>10,}")
    if cov["uncovered"] > 0:
        print(f"\n  Weakest chapters:")
        by_ch = cov["by_chapter"]
        weak = sorted(by_ch.items(), key=lambda x: x[1]["pct"])[:5]
        for ch, d in weak:
            if d["pct"] < 100:
                print(f"    {ch}: {d['covered']}/{d['total']} ({d['pct']:.1f}%)")

    # ── FP Summary Table
    print(f"\n{'─── FALSE POSITIVE RATES ':─<{w}}")
    print(f"  {'Dataset':<30} {'FP rate':>10} {'FP count':>12} {'TP rate':>10}")
    print(f"  {'─' * 30} {'─' * 10} {'─' * 12} {'─' * 10}")

    print(f"  {'Dev (hand-crafted, 171 FP)':<30} {dev['fp_rate']:>9.1f}% {dev['fp_count']:>8}/{dev['fp_total']:<3} {dev['tp_rate']:>9.1f}%")

    if val:
        print(f"  {'Static validation (657 FP)':<30} {val['fp_rate']:>9.1f}% {val['fp_count']:>8}/{val['fp_total']:<3} {val['tp_rate']:>9.1f}%")
    else:
        print(f"  {'Static validation':<30} {'N/A':>10}")

    adv_fp_total = adv.get("fp_total", 0)
    print(f"  {'Adversarial (dynamic, 460 FP)':<30} {adv['fp_rate']:>9.1f}% {adv['fp_count']:>8}/{adv_fp_total:<3} {adv['tp_rate']:>9.1f}%")

    # ── FP Breakdown by category
    print(f"\n{'─── FP BREAKDOWN BY CATEGORY ':─<{w}}")

    # Dev FP
    dev_cats = r["dev_fp"].get("by_category", {})
    print(f"\n  Dev FP categories:")
    for cat in sorted(dev_cats):
        d = dev_cats[cat]
        if d["matched"] > 0 or cat not in ("official_title", "natural_variant"):
            print(f"    {cat:<29} {d['matched']:>3}/{d['total']}")

    # Adversarial
    adv_cats = r["adversarial"].get("by_category", {})
    print(f"\n  Adversarial categories:")
    for cat in sorted(adv_cats):
        d = adv_cats[cat]
        if cat == "official_title":
            continue
        flag = "  ← FIX" if d["total"] > 0 and d["matched"] / d["total"] > 0.15 else ""
        print(f"    {cat:<29} {d['matched']:>3}/{d['total']}{flag}")

    # ── Sample FPs
    dev_fps = r["dev_fp"].get("false_positives_matched", [])
    adv_fps = r["adversarial"].get("false_positives_matched", [])

    if dev_fps:
        print(f"\n  Dev FP samples (first 10):")
        for fp in dev_fps[:10]:
            print(f"    [{fp['match_type']:14s}] \"{fp['text']}\"")

    if adv_fps:
        print(f"\n  Adversarial FP samples (first 10):")
        for fp in adv_fps[:10]:
            print(f"    [{fp['match_type']:14s}] \"{fp['text']}\"")

    # ── TP misses
    dev_tp_miss = r["dev_fp"].get("true_positives_missed", [])
    adv_tp_miss = r["adversarial"].get("true_positives_missed", [])
    if dev_tp_miss:
        print(f"\n  Dev TP misses ({len(dev_tp_miss)}):")
        for m in dev_tp_miss[:10]:
            print(f"    \"{m['text']}\"")
    if adv_tp_miss:
        print(f"\n  Adversarial TP misses ({len(adv_tp_miss)}):")
        for m in adv_tp_miss[:10]:
            print(f"    \"{m['text']}\"")

    # ── Context injection
    ctx = r["adversarial"].get("by_category", {}).get("context_injection", {})
    if ctx.get("total", 0) > 0:
        pct = 100 * ctx["matched"] / ctx["total"]
        print(f"\n  Context injection: {ctx['matched']}/{ctx['total']} matched ({pct:.0f}%)")
        print(f"  (Real titles wrapped in sentences — high match rate expected here)")

    # ── Composite
    print(f"\n{'─── COMPOSITE SCORE ':─<{w}}")
    cov_pct = cov["coverage_pct"]
    dev_fp_rate = dev["fp_rate"]
    adv_fp_rate = adv["fp_rate"]
    val_fp_rate = val.get("fp_rate", adv_fp_rate)
    size_kb = es["file_size_kb"]

    # Weighted: coverage 35%, dev FP 15%, static val FP 15%, adversarial FP 25%, size 10%
    size_score = max(0, 100 - (size_kb / 50))
    composite = (
        cov_pct * 0.35
        + (100 - dev_fp_rate) * 0.15
        + (100 - val_fp_rate) * 0.15
        + (100 - adv_fp_rate) * 0.25
        + size_score * 0.10
    )
    print(f"  Coverage (35%):       {cov_pct:>6.1f}")
    print(f"  Dev FP inv (15%):     {100 - dev_fp_rate:>6.1f}")
    print(f"  Val FP inv (15%):     {100 - val_fp_rate:>6.1f}")
    print(f"  Adv FP inv (25%):     {100 - adv_fp_rate:>6.1f}")
    print(f"  Size score (10%):     {size_score:>6.1f}")
    print(f"  ────────────────────────────")
    print(f"  COMPOSITE:            {composite:>6.1f}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Standardized ICD-10-CM entity evaluation")
    parser.add_argument("entity_xml", help="Path to entity XML file")
    parser.add_argument("--output", "-o", help="Output report JSON")
    parser.add_argument("--seed", type=int, default=42, help="Adversarial seed (default: 42)")
    args = parser.parse_args()

    results = run_full_report(args.entity_xml, adversarial_seed=args.seed)
    print_report(results)

    output = args.output or str(Path(args.entity_xml).parent / "report.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Full report written to {output}")


if __name__ == "__main__":
    main()
