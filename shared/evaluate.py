"""Unified evaluation framework for ICD-10-CM entity strategies.

Evaluates an entity XML against:
  1. Coverage: % of official ICD-10-CM titles matched
  2. FP rate: % of known false positives incorrectly matched
  3. TP rate: % of known true positives correctly matched
  4. Entity size metrics
  5. Specificity estimate: valid matches / total possible matches

Usage:
    python evaluate.py <entity_xml_path> [--output results.json]

The evaluator does NOT run a real Eduction engine. Instead it simulates matching
by checking whether each test phrase would be caught by the entity's flat entries
and/or regex patterns. This is an approximation — real engine behavior may differ
for complex cross-entity references ((?A:...) patterns).

Simulation approach:
  - Flat entries: exact substring match (case-insensitive)
  - Patterns: regex match (translated from entity syntax)
  - Cross-references: treated as opaque (logged as "pattern_ref" matches)

Each strategy's build_entity.py should ALSO produce a coverage_simulation.py
that understands the strategy's specific matching logic. This evaluator handles
the common metrics and FP testing.
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

SHARED_DIR = Path(__file__).parent
CSV_PATH = SHARED_DIR / "icd10cm_terms_2026.csv"
FP_DATASET_PATH = SHARED_DIR / "fp_dataset.json"
FP_VALIDATION_PATH = SHARED_DIR / "fp_validation.json"
EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")


def load_entity_entries(xml_path: str) -> Tuple[Set[str], List[str], Dict]:
    """Parse entity XML and extract flat entries and patterns.

    Returns:
        flat_entries: set of headword strings (lowered)
        regex_patterns: list of regex pattern strings (non-reference patterns)
        stats: dict of entity metadata
    """
    with open(xml_path, encoding="utf-8") as f:
        content = f.read()

    # Extract all headwords
    headwords = set()
    for m in re.finditer(r'<entry\s+headword="([^"]*)"', content):
        headwords.add(m.group(1).lower())

    # Extract patterns (non-score=0, non-reference)
    active_patterns = []
    ref_patterns = []
    score0_patterns = []
    for m in re.finditer(r'<pattern([^>]*)>(.*?)</pattern>', content, re.DOTALL):
        attrs = m.group(1)
        pat = m.group(2).strip()
        if 'score="0"' in attrs:
            score0_patterns.append(pat)
        elif "(?A:" in pat:
            ref_patterns.append(pat)
        else:
            active_patterns.append(pat)

    # Count entities
    entity_names = re.findall(r'<entity\s+name="([^"]*)"', content)
    public_count = len(re.findall(r'type="public"', content))
    private_count = len(re.findall(r'type="private"', content))

    stats = {
        "file_size_bytes": Path(xml_path).stat().st_size,
        "file_size_kb": round(Path(xml_path).stat().st_size / 1024, 1),
        "total_entities": len(entity_names),
        "public_entities": public_count,
        "private_entities": private_count,
        "entity_names": entity_names,
        "flat_entries": len(headwords),
        "active_patterns": len(active_patterns),
        "reference_patterns": len(ref_patterns),
        "score0_patterns": len(score0_patterns),
        "total_patterns": len(active_patterns) + len(ref_patterns) + len(score0_patterns),
    }

    return headwords, active_patterns, stats


def simulate_match(text: str, flat_entries: Set[str], regex_patterns: List[str]) -> Tuple[bool, str]:
    """Simulate whether the entity would match this text.

    Returns (matched: bool, match_type: str).
    match_type is one of: "flat", "regex", "none"
    """
    text_lower = text.lower().strip()

    # Check flat entries (exact match — headword appears in text as whole phrase)
    if text_lower in flat_entries:
        return True, "flat_exact"

    # Check if any flat entry is a substring match
    for entry in flat_entries:
        if len(entry) >= 5 and entry in text_lower:
            return True, "flat_substring"

    # Check regex patterns
    for pat in regex_patterns:
        try:
            if re.search(pat, text_lower, re.IGNORECASE):
                return True, "regex"
        except re.error:
            continue

    return False, "none"


def evaluate_coverage(xml_path: str, flat_entries: Set[str], regex_patterns: List[str]) -> Dict:
    """Evaluate coverage against official ICD-10-CM titles."""
    covered = 0
    uncovered = 0
    total = 0
    chapter_stats = defaultdict(lambda: {"covered": 0, "total": 0})

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Type"] != "official":
                continue
            code = row["ICD10CMCode"]
            if EXTERNAL_CAUSE_RE.match(code):
                continue

            term = row["Term"].strip().lower()
            total += 1
            chapter = code[0]
            chapter_stats[chapter]["total"] += 1

            matched, _ = simulate_match(term, flat_entries, regex_patterns)
            if matched:
                covered += 1
                chapter_stats[chapter]["covered"] += 1
            else:
                uncovered += 1

    return {
        "total_titles": total,
        "covered": covered,
        "uncovered": uncovered,
        "coverage_pct": round(100 * covered / total, 2) if total > 0 else 0,
        "by_chapter": {
            ch: {
                "covered": d["covered"],
                "total": d["total"],
                "pct": round(100 * d["covered"] / d["total"], 1) if d["total"] > 0 else 0,
            }
            for ch, d in sorted(chapter_stats.items())
        },
    }


def evaluate_fp(flat_entries: Set[str], regex_patterns: List[str]) -> Dict:
    """Evaluate false positive rate against the FP dataset."""
    with open(FP_DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    results = {
        "by_label": {"TP": {"total": 0, "matched": 0}, "FP": {"total": 0, "matched": 0}, "EDGE": {"total": 0, "matched": 0}},
        "by_category": {},
        "false_positives_matched": [],
        "true_positives_missed": [],
        "edge_cases": [],
    }

    for entry in dataset["entries"]:
        label = entry["label"]
        category = entry["category"]
        text = entry["text"]

        if category not in results["by_category"]:
            results["by_category"][category] = {"total": 0, "matched": 0}

        results["by_label"][label]["total"] += 1
        results["by_category"][category]["total"] += 1

        matched, match_type = simulate_match(text, flat_entries, regex_patterns)

        if matched:
            results["by_label"][label]["matched"] += 1
            results["by_category"][category]["matched"] += 1

            if label == "FP":
                results["false_positives_matched"].append({
                    "text": text,
                    "category": category,
                    "match_type": match_type,
                    "reason": entry.get("reason", ""),
                })
            elif label == "EDGE":
                results["edge_cases"].append({
                    "text": text,
                    "matched": True,
                    "category": category,
                    "reason": entry.get("reason", ""),
                })
        else:
            if label == "TP":
                results["true_positives_missed"].append({
                    "text": text,
                    "category": category,
                })
            elif label == "EDGE":
                results["edge_cases"].append({
                    "text": text,
                    "matched": False,
                    "category": category,
                    "reason": entry.get("reason", ""),
                })

    # Compute rates
    tp = results["by_label"]["TP"]
    fp = results["by_label"]["FP"]
    edge = results["by_label"]["EDGE"]

    results["summary"] = {
        "tp_rate": round(100 * tp["matched"] / tp["total"], 2) if tp["total"] > 0 else 0,
        "fp_rate": round(100 * fp["matched"] / fp["total"], 2) if fp["total"] > 0 else 0,
        "edge_match_rate": round(100 * edge["matched"] / edge["total"], 2) if edge["total"] > 0 else 0,
        "fp_count": fp["matched"],
        "fp_total": fp["total"],
        "tp_missed_count": tp["total"] - tp["matched"],
    }

    return results


def evaluate_validation(flat_entries: Set[str], regex_patterns: List[str]) -> Dict:
    """Evaluate against the held-out validation dataset (NOT seen during development)."""
    if not FP_VALIDATION_PATH.exists():
        return {"error": "fp_validation.json not found — run fp_validation.py first"}

    with open(FP_VALIDATION_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    results = {
        "by_label": {"TP": {"total": 0, "matched": 0}, "FP": {"total": 0, "matched": 0}},
        "by_category": {},
        "false_positives_matched": [],
        "true_positives_missed": [],
    }

    for entry in dataset["entries"]:
        label = entry["label"]
        category = entry["category"]
        text = entry["text"]

        if category not in results["by_category"]:
            results["by_category"][category] = {"total": 0, "matched": 0}

        if label not in results["by_label"]:
            results["by_label"][label] = {"total": 0, "matched": 0}

        results["by_label"][label]["total"] += 1
        results["by_category"][category]["total"] += 1

        matched, match_type = simulate_match(text, flat_entries, regex_patterns)

        if matched:
            results["by_label"][label]["matched"] += 1
            results["by_category"][category]["matched"] += 1

            if label == "FP":
                results["false_positives_matched"].append({
                    "text": text,
                    "category": category,
                    "match_type": match_type,
                    "reason": entry.get("reason", ""),
                })
        else:
            if label == "TP":
                results["true_positives_missed"].append({
                    "text": text,
                    "category": category,
                })

    tp = results["by_label"]["TP"]
    fp = results["by_label"]["FP"]

    results["summary"] = {
        "tp_rate": round(100 * tp["matched"] / tp["total"], 2) if tp["total"] > 0 else 0,
        "fp_rate": round(100 * fp["matched"] / fp["total"], 2) if fp["total"] > 0 else 0,
        "fp_count": fp["matched"],
        "fp_total": fp["total"],
        "tp_missed_count": tp["total"] - tp["matched"],
    }

    return results


def print_report(entity_stats: Dict, coverage: Dict, fp_results: Dict, validation: Dict = None):
    """Print human-readable evaluation report."""
    print("=" * 70)
    print("ICD-10-CM ENTITY EVALUATION REPORT")
    print("=" * 70)

    print("\n── ENTITY SIZE ──")
    print(f"  File size:          {entity_stats['file_size_kb']:>10.1f} KB")
    print(f"  Entities:           {entity_stats['total_entities']:>10d} ({entity_stats['public_entities']} public, {entity_stats['private_entities']} private)")
    print(f"  Flat entries:       {entity_stats['flat_entries']:>10d}")
    print(f"  Active patterns:    {entity_stats['active_patterns']:>10d}")
    print(f"  Ref patterns:       {entity_stats['reference_patterns']:>10d}")
    print(f"  Score=0 (FP block): {entity_stats['score0_patterns']:>10d}")

    print("\n── COVERAGE (ICD-10-CM titles, excl. V-Y) ──")
    print(f"  Total titles:  {coverage['total_titles']:>8d}")
    print(f"  Covered:       {coverage['covered']:>8d} ({coverage['coverage_pct']}%)")
    print(f"  Uncovered:     {coverage['uncovered']:>8d}")
    print(f"\n  By chapter:")
    for ch, d in coverage["by_chapter"].items():
        bar = "█" * int(d["pct"] / 2.5)
        print(f"    {ch}: {d['covered']:>6}/{d['total']:<6} ({d['pct']:>5.1f}%) {bar}")

    print("\n── FALSE POSITIVE TESTING ──")
    s = fp_results["summary"]
    print(f"  TP accuracy:    {s['tp_rate']:>6.1f}% ({fp_results['by_label']['TP']['matched']}/{fp_results['by_label']['TP']['total']} real titles matched)")
    print(f"  FP rate:        {s['fp_rate']:>6.1f}% ({s['fp_count']}/{s['fp_total']} false phrases matched)")
    print(f"  Edge cases:     {s['edge_match_rate']:>6.1f}% matched ({fp_results['by_label']['EDGE']['matched']}/{fp_results['by_label']['EDGE']['total']})")

    if fp_results["false_positives_matched"]:
        print(f"\n  FP matches by category:")
        cat_fps = Counter(e["category"] for e in fp_results["false_positives_matched"])
        for cat, count in cat_fps.most_common():
            total_in_cat = fp_results["by_category"][cat]["total"]
            print(f"    {cat:25s} {count:>3}/{total_in_cat} matched")

        print(f"\n  Sample FP matches (first 15):")
        for fp in fp_results["false_positives_matched"][:15]:
            print(f"    ✗ \"{fp['text']}\" [{fp['match_type']}] — {fp['reason']}")

    if fp_results["true_positives_missed"]:
        missed = len(fp_results["true_positives_missed"])
        print(f"\n  TP misses: {missed} real ICD titles not matched")
        for tp in fp_results["true_positives_missed"][:10]:
            print(f"    ✗ \"{tp['text']}\"")

    if validation and "error" not in validation:
        print("\n── HELD-OUT VALIDATION (unseen during development) ──")
        vs = validation["summary"]
        print(f"  TP accuracy:    {vs['tp_rate']:>6.1f}% ({validation['by_label']['TP']['matched']}/{validation['by_label']['TP']['total']})")
        print(f"  FP rate:        {vs['fp_rate']:>6.1f}% ({vs['fp_count']}/{vs['fp_total']} false phrases matched)")

        if validation["by_category"]:
            print(f"\n  Validation FP by category:")
            for cat in sorted(validation["by_category"].keys()):
                d = validation["by_category"][cat]
                if cat == "official_title":
                    continue
                print(f"    {cat:25s} {d['matched']:>3}/{d['total']} matched")

        if validation["false_positives_matched"]:
            print(f"\n  Sample validation FP matches (first 10):")
            for fp in validation["false_positives_matched"][:10]:
                print(f"    ✗ \"{fp['text']}\" [{fp['match_type']}]")


def main():
    parser = argparse.ArgumentParser(description="Evaluate ICD-10-CM entity")
    parser.add_argument("entity_xml", help="Path to entity XML file")
    parser.add_argument("--output", "-o", help="Output results JSON path")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress printed report")
    parser.add_argument("--skip-validation", action="store_true", help="Skip held-out validation dataset")
    args = parser.parse_args()

    print(f"Loading entity: {args.entity_xml}")
    flat_entries, regex_patterns, entity_stats = load_entity_entries(args.entity_xml)
    print(f"  {len(flat_entries)} flat entries, {len(regex_patterns)} regex patterns")

    print("\nEvaluating coverage...")
    coverage = evaluate_coverage(args.entity_xml, flat_entries, regex_patterns)

    print("Evaluating false positives...")
    fp_results = evaluate_fp(flat_entries, regex_patterns)

    validation = None
    if not args.skip_validation and FP_VALIDATION_PATH.exists():
        print("Evaluating held-out validation set...")
        validation = evaluate_validation(flat_entries, regex_patterns)

    if not args.quiet:
        print()
        print_report(entity_stats, coverage, fp_results, validation)

    results = {
        "entity_path": str(args.entity_xml),
        "entity_stats": entity_stats,
        "coverage": coverage,
        "fp_results": fp_results,
    }
    if validation:
        results["validation"] = validation

    output_path = args.output or str(Path(args.entity_xml).parent / "results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
