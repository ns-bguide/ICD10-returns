"""Adversarial FP validation — generates test phrases DYNAMICALLY at eval time.

The fp_dataset.json and fp_validation.json are STATIC files that builders can
read and optimize against. This module generates FP test phrases on the fly
from the ICD vocabulary itself, making it impossible to memorize the test set.

The core insight: any entity that achieves high coverage by including flat
entries or broad patterns can be stress-tested by recombining vocabulary from
the ICD-10-CM data itself. If "fracture" and "liver" both appear in the
entity (via entries or patterns), the entity likely matches "fracture of liver".

Tests:
  1. VOCAB_RECOMBINATION: Extract conditions and anatomies from the ENTITY ITSELF
     (not the CSV), then generate all pairwise "condition of anatomy" combos.
     Any that aren't real ICD titles are false positives.
  2. WORD_SOUP: Take random 2-4 word subsequences from the entity's flat entries
     and concatenate them. Most will be nonsense.
  3. AFFIX_PROBE: Generate plausible medical-looking words using known morphological
     affixes that don't exist in any medical vocabulary.
  4. CONTEXT_INJECTION: Wrap real ICD titles in conversational/clinical contexts
     to test whether the entity over-matches in running text.

Usage:
    python3 adversarial_validation.py <entity_xml_path> [--output results.json]
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

SHARED_DIR = Path(__file__).parent
CSV_PATH = SHARED_DIR / "icd10cm_terms_2026.csv"
EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")


def load_official_titles() -> Set[str]:
    titles = set()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Type"] == "official" and not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                titles.add(row["Term"].strip().lower())
    return titles


def load_all_terms() -> Set[str]:
    terms = set()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                terms.add(row["Term"].strip().lower())
    return terms


def load_entity_entries(xml_path: str) -> Tuple[Set[str], List[str]]:
    with open(xml_path, encoding="utf-8") as f:
        content = f.read()
    headwords = set()
    for m in re.finditer(r'<entry\s+headword="([^"]*)"', content):
        headwords.add(m.group(1).lower())
    patterns = []
    for m in re.finditer(r'<pattern([^>]*)>(.*?)</pattern>', content, re.DOTALL):
        attrs = m.group(1)
        pat = m.group(2).strip()
        if 'score="0"' not in attrs and "(?A:" not in pat:
            patterns.append(pat)
    return headwords, patterns


def simulate_match(text: str, flat_entries: Set[str], regex_patterns: List[str]) -> Tuple[bool, str]:
    text_lower = text.lower().strip()
    if text_lower in flat_entries:
        return True, "flat_exact"
    for entry in flat_entries:
        if len(entry) >= 5 and entry in text_lower:
            return True, "flat_substring"
    for pat in regex_patterns:
        try:
            if re.search(pat, text_lower, re.IGNORECASE):
                return True, "regex"
        except re.error:
            continue
    return False, "none"


# ── Test 1: Vocabulary Recombination ─────────────────────────────────

CONDITION_INDICATORS = [
    "fracture", "dislocation", "subluxation", "sprain", "strain",
    "laceration", "contusion", "abrasion", "burn", "corrosion",
    "hemorrhage", "rupture", "stenosis", "occlusion", "embolism",
    "thrombosis", "neoplasm", "abscess", "ulcer", "hernia", "prolapse",
    "cyst", "polyp", "gangrene", "necrosis", "fibrosis", "sclerosis",
    "edema", "effusion", "atrophy", "hypertrophy", "degeneration",
    "infection", "inflammation", "disorder", "disease", "syndrome",
    "cataract", "glaucoma", "retinopathy", "neuropathy", "myelopathy",
    "osteomyelitis", "osteonecrosis", "osteoporosis", "arthritis",
    "dermatitis", "hepatitis", "nephritis", "pneumonia", "bronchitis",
]

ANATOMY_INDICATORS = [
    "femur", "tibia", "fibula", "patella", "humerus", "radius", "ulna",
    "clavicle", "scapula", "pelvis", "sacrum", "skull", "vertebra",
    "knee", "hip", "shoulder", "ankle", "elbow", "wrist",
    "liver", "kidney", "lung", "brain", "heart", "spleen", "pancreas",
    "stomach", "esophagus", "bladder", "colon", "rectum",
    "eye", "cornea", "retina", "lens", "iris",
    "aorta", "coronary artery", "femoral artery", "pulmonary artery",
    "spinal cord", "sciatic nerve", "brachial plexus",
    "uterus", "ovary", "cervix", "prostate", "testis",
    "skin", "scalp", "face", "trunk", "hand", "foot",
]


def gen_vocab_recombination(
    flat_entries: Set[str], official_titles: Set[str], all_terms: Set[str],
    seed: int, n: int = 300
) -> List[dict]:
    """Recombine conditions and anatomies extracted from the entity's own entries."""
    rng = random.Random(seed)

    entity_conditions = set()
    entity_anatomies = set()
    for entry in flat_entries:
        entry_words = set(entry.split())
        for cond in CONDITION_INDICATORS:
            if cond in entry or cond in entry_words:
                entity_conditions.add(cond)
        for anat in ANATOMY_INDICATORS:
            if anat in entry:
                entity_anatomies.add(anat)

    if not entity_conditions or not entity_anatomies:
        return []

    conditions = sorted(entity_conditions)
    anatomies = sorted(entity_anatomies)

    entries = []
    seen = set()
    attempts = 0
    while len(entries) < n and attempts < n * 30:
        attempts += 1
        c = rng.choice(conditions)
        a = rng.choice(anatomies)
        phrase = f"{c} of {a}"
        if phrase in official_titles or phrase in all_terms or phrase in seen:
            continue
        seen.add(phrase)
        entries.append({
            "text": phrase,
            "label": "FP",
            "category": "vocab_recombination",
            "reason": f"entity contains both '{c}' and '{a}' but '{phrase}' is not a real ICD title",
        })
    return entries


# ── Test 2: Word Soup ────────────────────────────────────────────────

def gen_word_soup(
    flat_entries: Set[str], official_titles: Set[str],
    seed: int, n: int = 100
) -> List[dict]:
    """Random multi-word subsequences from entity entries concatenated."""
    rng = random.Random(seed)

    all_words = set()
    for entry in flat_entries:
        for w in entry.split():
            if len(w) >= 4 and not w.isdigit():
                all_words.add(w)

    words = sorted(all_words)
    if len(words) < 10:
        return []

    entries = []
    seen = set()
    attempts = 0
    while len(entries) < n and attempts < n * 30:
        attempts += 1
        k = rng.randint(2, 4)
        chosen = [rng.choice(words) for _ in range(k)]
        phrase = " ".join(chosen)
        if phrase in official_titles or phrase in seen or len(phrase) < 8:
            continue
        seen.add(phrase)
        entries.append({
            "text": phrase,
            "label": "FP",
            "category": "word_soup",
            "reason": f"random word concatenation from entity vocabulary",
        })
    return entries


# ── Test 3: Affix Probe ──────────────────────────────────────────────

MEDICAL_PREFIXES = [
    "hyper", "hypo", "pseudo", "para", "peri", "inter", "intra",
    "retro", "supra", "infra", "sub", "trans", "endo", "exo",
]

MEDICAL_SUFFIXES = [
    "itis", "osis", "emia", "pathy", "algia", "uria", "opia",
    "megaly", "plegia", "spasm", "cele", "malacia", "dynia",
]

FAKE_ROOTS = [
    "plax", "trem", "vect", "cron", "blex", "strop", "flam",
    "grypt", "phren", "volut", "dract", "clav", "morp",
    "sphen", "graph", "chrom", "galv", "therm", "pneum",
]


def gen_affix_probes(official_titles: Set[str], seed: int, n: int = 60) -> List[dict]:
    """Generate plausible medical-sounding words that don't actually exist."""
    rng = random.Random(seed)
    entries = []
    seen = set()
    attempts = 0

    while len(entries) < n and attempts < n * 20:
        attempts += 1
        prefix = rng.choice(MEDICAL_PREFIXES) if rng.random() < 0.5 else ""
        root = rng.choice(FAKE_ROOTS)
        suffix = rng.choice(MEDICAL_SUFFIXES)
        word = f"{prefix}{root}{suffix}"
        if word in seen or word in official_titles or len(word) < 6:
            continue
        seen.add(word)
        entries.append({
            "text": word,
            "label": "FP",
            "category": "affix_probe",
            "reason": f"synthetic medical-sounding word: {prefix}+{root}+{suffix}",
        })
    return entries


# ── Test 4: Context Injection ────────────────────────────────────────

CONTEXT_TEMPLATES = [
    "patient denies {title}",
    "no evidence of {title}",
    "family history of {title}",
    "risk factors for {title}",
    "the {title} was managed conservatively",
    "status post treatment for {title}",
    "rule out {title}",
    "differential diagnosis includes {title}",
    "she was diagnosed with {title} last year",
    "he presented with possible {title}",
    "unlikely {title}",
    "resolved {title}",
    "history of {title} in childhood",
    "mother had {title}",
    "screening for {title}",
]


def gen_context_injection(
    official_titles: Set[str], seed: int, n: int = 80
) -> List[dict]:
    """Wrap real ICD titles in conversational/clinical context."""
    rng = random.Random(seed)
    titles_list = sorted(official_titles)
    rng.shuffle(titles_list)

    entries = []
    for title in titles_list[:n]:
        template = rng.choice(CONTEXT_TEMPLATES)
        phrase = template.format(title=title)
        if phrase not in official_titles:
            entries.append({
                "text": phrase,
                "label": "CONTEXT",
                "category": "context_injection",
                "original_title": title,
                "reason": f"real title wrapped in clinical context",
            })
    return entries


# ── Test 5: True Positives (fresh sample) ────────────────────────────

def gen_true_positives(official_titles: Set[str], seed: int, n: int = 200) -> List[dict]:
    rng = random.Random(seed)
    titles_list = sorted(official_titles)
    rng.shuffle(titles_list)
    return [{"text": t, "label": "TP", "category": "official_title"} for t in titles_list[:n]]


# ── Main evaluation ──────────────────────────────────────────────────

def run_adversarial_validation(xml_path: str, seed: int = None) -> Dict:
    if seed is None:
        seed = hash(Path(xml_path).stat().st_mtime_ns) % 2**31

    print(f"Loading entity: {xml_path}")
    flat_entries, regex_patterns = load_entity_entries(xml_path)
    print(f"  {len(flat_entries)} flat entries, {len(regex_patterns)} regex patterns")

    print("Loading ICD titles...")
    official_titles = load_official_titles()
    all_terms = load_all_terms()

    print(f"Generating adversarial tests (seed={seed})...")
    tp_entries = gen_true_positives(official_titles, seed, n=200)
    vocab_recombo = gen_vocab_recombination(flat_entries, official_titles, all_terms, seed, n=300)
    word_soup = gen_word_soup(flat_entries, official_titles, seed, n=100)
    affix_probes = gen_affix_probes(official_titles, seed, n=60)
    context_inj = gen_context_injection(official_titles, seed, n=80)

    all_tests = tp_entries + vocab_recombo + word_soup + affix_probes + context_inj

    print(f"  {len(tp_entries)} true positives")
    print(f"  {len(vocab_recombo)} vocab recombinations")
    print(f"  {len(word_soup)} word soup")
    print(f"  {len(affix_probes)} affix probes")
    print(f"  {len(context_inj)} context injections")

    # Run matches
    results_by_label = defaultdict(lambda: {"total": 0, "matched": 0})
    results_by_category = defaultdict(lambda: {"total": 0, "matched": 0})
    fp_matched = []
    tp_missed = []
    context_matched = []

    for entry in all_tests:
        label = entry["label"]
        cat = entry["category"]
        text = entry["text"]

        results_by_label[label]["total"] += 1
        results_by_category[cat]["total"] += 1

        matched, match_type = simulate_match(text, flat_entries, regex_patterns)

        if matched:
            results_by_label[label]["matched"] += 1
            results_by_category[cat]["matched"] += 1

            if label == "FP":
                fp_matched.append({
                    "text": text,
                    "category": cat,
                    "match_type": match_type,
                    "reason": entry.get("reason", ""),
                })
            elif label == "CONTEXT":
                context_matched.append({
                    "text": text,
                    "match_type": match_type,
                    "original_title": entry.get("original_title", ""),
                })
        else:
            if label == "TP":
                tp_missed.append({"text": text, "category": cat})

    fp = results_by_label["FP"]
    tp = results_by_label["TP"]
    ctx = results_by_label.get("CONTEXT", {"total": 0, "matched": 0})

    summary = {
        "seed": seed,
        "tp_rate": round(100 * tp["matched"] / tp["total"], 2) if tp["total"] else 0,
        "fp_rate": round(100 * fp["matched"] / fp["total"], 2) if fp["total"] else 0,
        "fp_count": fp["matched"],
        "fp_total": fp["total"],
        "tp_missed_count": tp["total"] - tp["matched"],
        "context_match_rate": round(100 * ctx["matched"] / ctx["total"], 2) if ctx["total"] else 0,
    }

    return {
        "summary": summary,
        "by_label": dict(results_by_label),
        "by_category": dict(results_by_category),
        "false_positives_matched": fp_matched,
        "true_positives_missed": tp_missed,
        "context_matches": context_matched,
    }


def print_report(results: Dict):
    s = results["summary"]
    print()
    print("=" * 70)
    print("ADVERSARIAL VALIDATION REPORT")
    print("=" * 70)
    print(f"  Seed: {s['seed']}")
    print(f"\n  TP accuracy:    {s['tp_rate']:>6.1f}% ({results['by_label']['TP']['matched']}/{results['by_label']['TP']['total']})")
    print(f"  FP rate:        {s['fp_rate']:>6.1f}% ({s['fp_count']}/{s['fp_total']})")
    print(f"  Context match:  {s['context_match_rate']:>6.1f}%")

    print(f"\n  FP by category:")
    for cat in sorted(results["by_category"]):
        d = results["by_category"][cat]
        if cat == "official_title":
            continue
        marker = " !!!" if d["matched"] > d["total"] * 0.15 else ""
        print(f"    {cat:25s} {d['matched']:>3}/{d['total']}{marker}")

    if results["false_positives_matched"]:
        print(f"\n  Sample FP matches (first 15):")
        for fp in results["false_positives_matched"][:15]:
            print(f"    [{fp['match_type']:14s}] \"{fp['text']}\"")

    if results["true_positives_missed"]:
        print(f"\n  TP misses ({len(results['true_positives_missed'])}):")
        for tp in results["true_positives_missed"][:10]:
            print(f"    \"{tp['text']}\"")


def main():
    parser = argparse.ArgumentParser(description="Adversarial FP validation")
    parser.add_argument("entity_xml", help="Path to entity XML file")
    parser.add_argument("--output", "-o", help="Output results JSON")
    parser.add_argument("--seed", "-s", type=int, default=None, help="Random seed (default: derived from file mtime)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    results = run_adversarial_validation(args.entity_xml, seed=args.seed)

    if not args.quiet:
        print_report(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
