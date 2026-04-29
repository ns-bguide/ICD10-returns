"""Side-by-side comparison of strategy evaluation results.

Usage:
    python compare.py                          # auto-discover results
    python compare.py path/to/a.json path/to/b.json ...
    python compare.py --output comparison.json  # also save structured output
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def discover_results():
    """Auto-discover report.json / results.json in strategy and baseline dirs."""
    found = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name == "shared":
            continue
        for name in ("report.json", "results.json"):
            p = d / name
            if p.exists():
                found.append(p)
                break
    return found


DEFAULT_RESULTS = discover_results()


def load_results(paths):
    results = {}
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        label = p.parent.name
        results[label] = data
    return results


def fmt_pct(val):
    return f"{val:>6.1f}%"


def fmt_int(val):
    return f"{val:>8,}"


def print_comparison(results):
    labels = list(results.keys())
    if not labels:
        print("No results found. Run evaluations first.")
        return

    col_width = max(22, max(len(l) for l in labels) + 2)
    header = f"{'Metric':<35}" + "".join(f"{l:>{col_width}}" for l in labels)

    print("=" * len(header))
    print("ICD-10-CM ENTITY STRATEGY COMPARISON")
    print("=" * len(header))
    print()
    print(header)
    print("-" * len(header))

    # Entity size
    print("\n── ENTITY SIZE ──")
    for metric, key in [
        ("File size (KB)", "file_size_kb"),
        ("Total entities", "total_entities"),
        ("Flat entries", "flat_entries"),
        ("Active patterns", "active_patterns"),
        ("Ref patterns", "reference_patterns"),
        ("Score=0 (FP block)", "score0_patterns"),
    ]:
        vals = []
        for l in labels:
            v = results[l].get("entity_stats", {}).get(key, "—")
            if isinstance(v, float):
                vals.append(f"{v:>{col_width},.1f}")
            elif isinstance(v, int):
                vals.append(f"{v:>{col_width},}")
            else:
                vals.append(f"{str(v):>{col_width}}")
        print(f"  {metric:<33}" + "".join(vals))

    # Coverage
    print("\n── COVERAGE (ICD-10-CM titles, excl. V-Y) ──")
    for metric, key in [
        ("Total titles", "total_titles"),
        ("Covered", "covered"),
        ("Uncovered", "uncovered"),
        ("Coverage %", "coverage_pct"),
    ]:
        vals = []
        for l in labels:
            v = results[l].get("coverage", {}).get(key, "—")
            if key == "coverage_pct":
                vals.append(f"{v:>{col_width}.2f}%")
            elif isinstance(v, int):
                vals.append(f"{v:>{col_width},}")
            else:
                vals.append(f"{str(v):>{col_width}}")
        print(f"  {metric:<33}" + "".join(vals))

    # Chapter breakdown
    print("\n  By chapter:")
    all_chapters = set()
    for l in labels:
        all_chapters.update(results[l].get("coverage", {}).get("by_chapter", {}).keys())
    for ch in sorted(all_chapters):
        vals = []
        for l in labels:
            d = results[l].get("coverage", {}).get("by_chapter", {}).get(ch, {})
            if d:
                vals.append(f"{d['pct']:>{col_width - 1}.1f}%")
            else:
                vals.append(f"{'—':>{col_width}}")
        print(f"    {ch:<31}" + "".join(vals))

    # FP results
    print("\n── FALSE POSITIVE TESTING ──")
    for metric, key in [
        ("TP accuracy %", "tp_rate"),
        ("FP rate %", "fp_rate"),
        ("Edge match rate %", "edge_match_rate"),
        ("FP count", "fp_count"),
        ("TP missed count", "tp_missed_count"),
    ]:
        vals = []
        for l in labels:
            v = results[l].get("fp_results", {}).get("summary", {}).get(key, "—")
            if key in ("tp_rate", "fp_rate", "edge_match_rate"):
                vals.append(f"{v:>{col_width - 1}.2f}%")
            elif isinstance(v, int):
                vals.append(f"{v:>{col_width},}")
            else:
                vals.append(f"{str(v):>{col_width}}")
        print(f"  {metric:<33}" + "".join(vals))

    # FP by category
    print("\n  FP by category:")
    all_cats = set()
    for l in labels:
        fp_matched = results[l].get("fp_results", {}).get("false_positives_matched", [])
        for fp in fp_matched:
            all_cats.add(fp.get("category", "unknown"))
    for cat in sorted(all_cats):
        vals = []
        for l in labels:
            fp_matched = results[l].get("fp_results", {}).get("false_positives_matched", [])
            count = sum(1 for fp in fp_matched if fp.get("category") == cat)
            total_in_cat = results[l].get("fp_results", {}).get("by_category", {}).get(cat, {}).get("total", 0)
            if total_in_cat:
                vals.append(f"{count}/{total_in_cat}".rjust(col_width))
            else:
                vals.append(f"{'—':>{col_width}}")
        print(f"    {cat:<29}" + "".join(vals))

    # Validation results
    has_validation = any("validation" in results[l] for l in labels)
    if has_validation:
        print("\n── HELD-OUT VALIDATION (unseen during development) ──")
        for metric, key in [
            ("Validation TP rate %", "tp_rate"),
            ("Validation FP rate %", "fp_rate"),
            ("Validation FP count", "fp_count"),
        ]:
            vals = []
            for l in labels:
                v = results[l].get("validation", {}).get("summary", {}).get(key, "—")
                if isinstance(v, str):
                    vals.append(f"{v:>{col_width}}")
                elif key in ("tp_rate", "fp_rate"):
                    vals.append(f"{v:>{col_width - 1}.2f}%")
                elif isinstance(v, int):
                    vals.append(f"{v:>{col_width},}")
                else:
                    vals.append(f"{str(v):>{col_width}}")
            print(f"  {metric:<33}" + "".join(vals))

        print("\n  Validation FP by category:")
        val_cats = set()
        for l in labels:
            val_data = results[l].get("validation", {})
            if "by_category" in val_data:
                val_cats.update(k for k in val_data["by_category"] if k != "official_title")
        for cat in sorted(val_cats):
            vals = []
            for l in labels:
                d = results[l].get("validation", {}).get("by_category", {}).get(cat, {})
                if d:
                    vals.append(f"{d.get('matched', 0)}/{d.get('total', 0)}".rjust(col_width))
                else:
                    vals.append(f"{'—':>{col_width}}")
            print(f"    {cat:<29}" + "".join(vals))

    # Composite score
    print("\n── COMPOSITE SCORE ──")
    print("  (coverage_pct * 0.4 + (100 - dev_fp) * 0.2 + (100 - val_fp) * 0.3 + size_penalty * 0.1)")
    for l in labels:
        cov = results[l].get("coverage", {}).get("coverage_pct", 0)
        dev_fp = results[l].get("fp_results", {}).get("summary", {}).get("fp_rate", 100)
        val_fp = results[l].get("validation", {}).get("summary", {}).get("fp_rate", dev_fp)
        size_kb = results[l].get("entity_stats", {}).get("file_size_kb", 10000)
        size_score = max(0, 100 - (size_kb / 50))
        composite = cov * 0.4 + (100 - dev_fp) * 0.2 + (100 - val_fp) * 0.3 + size_score * 0.1
        print(f"  {l:<33}{composite:>{col_width - 1}.1f}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Compare ICD-10-CM entity evaluations")
    parser.add_argument("results", nargs="*", help="Paths to results.json files")
    parser.add_argument("--output", "-o", help="Save comparison as JSON")
    args = parser.parse_args()

    paths = [Path(p) for p in args.results] if args.results else DEFAULT_RESULTS
    results = load_results(paths)

    if not results:
        print("No results found. Expected results.json in:")
        for p in paths:
            print(f"  {p}")
        sys.exit(1)

    print_comparison(results)

    if args.output:
        summary = {}
        for label, data in results.items():
            summary[label] = {
                "coverage_pct": data.get("coverage", {}).get("coverage_pct", 0),
                "fp_rate": data.get("fp_results", {}).get("summary", {}).get("fp_rate", 0),
                "tp_rate": data.get("fp_results", {}).get("summary", {}).get("tp_rate", 0),
                "validation_fp_rate": data.get("validation", {}).get("summary", {}).get("fp_rate", None),
                "validation_tp_rate": data.get("validation", {}).get("summary", {}).get("tp_rate", None),
                "file_size_kb": data.get("entity_stats", {}).get("file_size_kb", 0),
                "flat_entries": data.get("entity_stats", {}).get("flat_entries", 0),
                "active_patterns": data.get("entity_stats", {}).get("active_patterns", 0),
            }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Comparison saved to {args.output}")


if __name__ == "__main__":
    main()
