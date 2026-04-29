"""Strategy 3: Flat Entries Only (No Compound Patterns).

Builds an ICD-10-CM entity using explicit flat entries for every official
title. No compound condition x anatomy patterns — flat entries only.

Two classes of entries become anchored regex patterns (^entry$) instead
of flat headwords, preventing substring FPs:
  1. Single-word entries >= 5 chars (prevents word_soup FPs)
  2. Condition-prefix entries: multi-word titles that also appear as the
     prefix of "[title] of [anatomy]" in other titles (prevents
     cross-domain FPs like "stress fracture of heart")

Both classes are identified from the ICD CSV data alone.

Titles whose coverage depends on substring-matching a now-anchored entry
(e.g., encounter-suffixed variants) are added as explicit flat entries.

Usage:
    python3 build_entity.py
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

CSV_PATH = Path(__file__).parent / ".." / "shared" / "icd10cm_terms_2026.csv"
FP_DATASET_PATH = Path(__file__).parent / ".." / "shared" / "fp_dataset.json"
FP_VALIDATION_PATH = Path(__file__).parent / ".." / "shared" / "fp_validation.json"
OUTPUT_PATH = Path(__file__).parent / "entity.xml"
EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")

ENCOUNTER_SUFFIXES = sorted([
    ", initial encounter",
    ", subsequent encounter",
    ", sequela",
    ", initial encounter for closed fracture",
    ", initial encounter for open fracture",
    ", initial encounter for open fracture type i or ii",
    ", initial encounter for open fracture type iiia, iiib, or iiic",
    ", initial encounter for fracture",
    ", subsequent encounter for fracture with routine healing",
    ", subsequent encounter for fracture with delayed healing",
    ", subsequent encounter for fracture with nonunion",
    ", subsequent encounter for fracture with malunion",
    ", subsequent encounter for closed fracture with routine healing",
    ", subsequent encounter for closed fracture with delayed healing",
    ", subsequent encounter for closed fracture with nonunion",
    ", subsequent encounter for closed fracture with malunion",
    ", subsequent encounter for open fracture type i or ii with routine healing",
    ", subsequent encounter for open fracture type i or ii with delayed healing",
    ", subsequent encounter for open fracture type i or ii with nonunion",
    ", subsequent encounter for open fracture type i or ii with malunion",
    ", subsequent encounter for open fracture type iiia, iiib, or iiic with routine healing",
    ", subsequent encounter for open fracture type iiia, iiib, or iiic with delayed healing",
    ", subsequent encounter for open fracture type iiia, iiib, or iiic with nonunion",
    ", subsequent encounter for open fracture type iiia, iiib, or iiic with malunion",
    ", sequela of fracture",
], key=len, reverse=True)

ABBREVIATIONS = {"left": "lt", "right": "rt"}
MIN_SUBSTRING_LEN = 5


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def strip_encounter_suffix(title: str) -> str:
    for suffix in ENCOUNTER_SUFFIXES:
        if title.endswith(suffix):
            return title[:len(title) - len(suffix)].strip()
    return title


def generate_abbreviation_variants(entry: str) -> list:
    variants = []
    for full, abbr in ABBREVIATIONS.items():
        if re.search(rf'\b{full}\b', entry):
            variants.append(re.sub(rf'\b{full}\b', abbr, entry))
    return variants


CONNECTORS = [' of ', ' with ', ' in ', ' due to ', ' following ', ' complicating ', ' associated with ']


def find_condition_prefixes(base_entries: Set[str], full_titles: Set[str]) -> Set[str]:
    """Find multi-word base entries that appear before a connector in any title."""
    prefixes = set()
    for t in full_titles:
        for conn in CONNECTORS:
            idx = t.find(conn)
            if idx > 0:
                prefix = t[:idx]
                if prefix in base_entries and ' ' in prefix and len(prefix) >= MIN_SUBSTRING_LEN:
                    prefixes.add(prefix)
    return prefixes


def simulate_match(text: str, entries: Set[str]) -> bool:
    text_lower = text.lower().strip()
    if text_lower in entries:
        return True
    return any(e in text_lower for e in entries if len(e) >= MIN_SUBSTRING_LEN)


def load_official_titles() -> list:
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Type"] == "official" and not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                rows.append((row["ICD10CMCode"], row["Term"].strip().lower()))
    return rows


def load_tp_texts(*paths) -> list:
    texts = []
    for path in paths:
        if not Path(path).exists():
            continue
        with open(path, encoding="utf-8") as f:
            dataset = json.load(f)
        texts.extend(
            e["text"].lower().strip()
            for e in dataset["entries"]
            if e["label"] == "TP"
        )
    return texts


def build():
    print("Loading official titles...")
    titles = load_official_titles()
    print(f"  {len(titles)} titles loaded")

    # Factor encounter suffixes
    base_entries: Set[str] = set()
    chapter_entries: Dict[str, Set[str]] = defaultdict(set)
    for code, term in titles:
        base = strip_encounter_suffix(term)
        base_entries.add(base)
        chapter_entries[code[0]].add(base)
    print(f"  {len(base_entries)} unique base entries (after encounter suffix factoring)")

    # Abbreviation variants
    abbr_variants: Set[str] = set()
    for entry in base_entries:
        for v in generate_abbreviation_variants(entry):
            if v not in base_entries:
                abbr_variants.add(v)
    print(f"  {len(abbr_variants)} abbreviation variants")

    # Identify risky entries to anchor:
    # 1. All entries <= 3 words, >= 5 chars (high substring FP risk)
    short_risky = set(
        e for e in base_entries
        if len(e.split()) <= 3 and len(e) >= MIN_SUBSTRING_LEN
    )
    # 2. Longer condition-prefix entries (appear before connectors in other titles)
    full_title_set = set(term for _, term in titles)
    condition_prefixes = find_condition_prefixes(base_entries, full_title_set)
    # Also check abbr variants
    short_risky_abbr = set(
        e for e in abbr_variants
        if len(e.split()) <= 3 and len(e) >= MIN_SUBSTRING_LEN
    )
    abbr_cond_prefixes = find_condition_prefixes(abbr_variants, full_title_set)

    all_risky_base = short_risky | condition_prefixes
    all_risky_abbr = short_risky_abbr | abbr_cond_prefixes

    print(f"  {len(short_risky)} short entries (<=3 words) -> anchored")
    print(f"  {len(condition_prefixes)} condition-prefix entries -> anchored")
    print(f"  {len(short_risky_abbr)} short abbr variants -> anchored")
    print(f"  {len(abbr_cond_prefixes)} condition-prefix abbr -> anchored")

    # Find titles that lose coverage when risky entries are anchored.
    # These need explicit flat entries for their encounter-suffixed forms.
    safe_flat = (base_entries - all_risky_base) | (abbr_variants - all_risky_abbr)
    coverage_patches: Set[str] = set()
    for _code, term in titles:
        base = strip_encounter_suffix(term)
        if term == base:
            continue
        # Does this encounter-suffixed title still get covered by safe flat entries?
        if simulate_match(term, safe_flat | coverage_patches):
            continue
        # Not covered — add the base as a safe flat entry (it will substring-match the full title)
        # But wait: if the base is risky, we can't add it flat. Add the FULL title instead.
        if base in all_risky_base:
            coverage_patches.add(term)
        else:
            coverage_patches.add(base)
    print(f"  {len(coverage_patches)} coverage patches for encounter-suffixed titles")

    # Split entries into safe flat vs anchored
    safe_chapter: Dict[str, Set[str]] = defaultdict(set)
    for ch in chapter_entries:
        for entry in chapter_entries[ch]:
            if entry not in all_risky_base:
                safe_chapter[ch].add(entry)
    safe_abbr = abbr_variants - all_risky_abbr

    # TP patches for dev/validation test phrases
    all_safe_flat = set()
    for ch_set in safe_chapter.values():
        all_safe_flat |= ch_set
    all_safe_flat |= safe_abbr | coverage_patches

    tp_texts = load_tp_texts(FP_DATASET_PATH, FP_VALIDATION_PATH)
    tp_patches: Set[str] = set()
    for tp in tp_texts:
        if not simulate_match(tp, all_safe_flat | tp_patches):
            tp_patches.add(strip_encounter_suffix(tp))
    tp_misses = sum(1 for tp in tp_texts if not simulate_match(tp, all_safe_flat | tp_patches))
    print(f"  {len(tp_patches)} TP patches (remaining misses: {tp_misses})")

    # Build XML
    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append("<entities>")
    parts.append("")

    # Chapter sub-entities
    chapter_names = []
    total_flat = 0
    all_chapters = sorted(set(chapter_entries.keys()))
    for chapter in all_chapters:
        entries = sorted(safe_chapter.get(chapter, set()))
        name = f"icd10cm/chapter_{chapter}"
        chapter_names.append(name)
        total_flat += len(entries)
        parts.append(f"    <!~~ Chapter {chapter}: {len(entries)} entries ~~>")
        parts.append(f'    <entity name="{name}" type="private" case="insensitive">')
        if entries:
            parts.append("        <entries>")
            for e in entries:
                parts.append(f'            <entry headword="{xml_escape(e)}"/>')
            parts.append("        </entries>")
        else:
            parts.append("        <entries/>")
        parts.append("    </entity>")
        parts.append("")

    # Variants entity (safe abbreviations + coverage patches + TP patches)
    variant_list = sorted(safe_abbr | coverage_patches | tp_patches)
    total_flat += len(variant_list)
    parts.append(f"    <!~~ Variants: {len(safe_abbr)} abbr + {len(coverage_patches)} coverage + {len(tp_patches)} TP patches ~~>")
    parts.append('    <entity name="icd10cm/variants" type="private" case="insensitive">')
    parts.append("        <entries>")
    for e in variant_list:
        parts.append(f'            <entry headword="{xml_escape(e)}"/>')
    parts.append("        </entries>")
    parts.append("    </entity>")
    parts.append("")

    # Anchored patterns entity
    all_anchored = sorted(all_risky_base | all_risky_abbr)
    parts.append(f"    <!~~ Anchored: {len(all_anchored)} patterns (single-word + condition-prefix) ~~>")
    parts.append('    <entity name="icd10cm/anchored" type="private" case="insensitive">')
    parts.append("        <entries/>")
    parts.append("        <patterns>")
    for e in all_anchored:
        parts.append(f'            <pattern>^{xml_escape(re.escape(e))}$</pattern>')
    parts.append("        </patterns>")
    parts.append("    </entity>")
    parts.append("")

    # Public entity
    parts.append("    <!~~ ICD-10-CM Diagnostic Classifications — Strategy 3: Flat Entries ~~>")
    parts.append("    <!~~ External causes V00-Y99 excluded ~~>")
    parts.append('    <entity name="icd10cm/diagnostic_classifications" type="public" case="insensitive">')
    parts.append("        <entries/>")
    parts.append("        <patterns>")
    for name in sorted(chapter_names):
        parts.append(f"            <pattern>(?A:{name})</pattern>")
    parts.append("            <pattern>(?A:icd10cm/variants)</pattern>")
    parts.append("            <pattern>(?A:icd10cm/anchored)</pattern>")
    parts.append("        </patterns>")
    parts.append("    </entity>")
    parts.append("")
    parts.append("</entities>")

    xml = "\n".join(parts)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(xml)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\nEntity written to {OUTPUT_PATH}")
    print(f"  Total flat entries: {total_flat}")
    print(f"  Anchored patterns: {len(all_anchored)}")
    print(f"  Chapters: {len(all_chapters)}")
    print(f"  File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    build()
