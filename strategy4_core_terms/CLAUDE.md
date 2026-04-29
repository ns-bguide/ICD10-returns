# Strategy 4: Core Terms

## Goal

Build an ICD-10-CM entity XML that matches official diagnostic titles using a **pre-existing core terms list** provided by the builder. The core terms list is a curated vocabulary of medical phrases that the builder has already assembled independently of this project.

## The Problem You're Solving

The baseline entity achieves 99.5% coverage but has an **88% false positive rate**. Two root causes:

1. **Compound patterns** like `[condition] of [anatomy]` allow ANY condition to combine with ANY anatomy — producing nonsense like "fracture of liver", "hernia of cornea".
2. **Single-word flat entries** like "fracture", "viral", "chronic" match as substrings in unrelated text — "viral video", "chronic complainer".

Previous strategies solved this by either constraining compound patterns to valid domains (Strategy 1) or listing every ICD title explicitly (Strategy 3). This strategy uses your core terms list as its foundation.

## Your Input: The Core Terms List

You are expected to bring a **core terms list** — a file containing curated medical terms/phrases. Place it in this directory before building. Your `build_entity.py` should read this list and use it as the primary vocabulary for the entity.

The core terms list is your own work product. It may be:
- A flat text file (one term per line)
- A CSV or JSON file
- Any format you choose — just document it in your builder

Your `build_entity.py` will combine this list with the ICD-10-CM CSV data to build the entity. For example, you might:
- Use core terms as the matching vocabulary directly
- Cross-reference core terms against official ICD titles to validate coverage
- Supplement core terms with additional entries derived from the CSV to fill coverage gaps
- Apply structural FP prevention techniques (anchored patterns, length filtering)

## Source Data

- **Your core terms list** — place it in this directory
- **CSV**: `../shared/icd10cm_terms_2026.csv` — 445K rows, 97K official titles
  - Columns: `ICD10CMCode`, `Term`, `Type`
  - Use `Type == "official"` for coverage targets (~86,827 excluding V-Y)
  - Exclude codes starting with V, W, X, Y (external causes)
- **Reference entity**: `../shared/medical_conditions.xml` — existing healthcare entity for architectural patterns (DO NOT modify)

## Entity XML Format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entities>
    <!-- Private sub-entity -->
    <entity name="icd10cm/core_conditions" type="private" case="insensitive">
        <entries>
            <entry headword="fracture of femur"/>
            <entry headword="chronic kidney disease"/>
        </entries>
    </entity>

    <!-- Public entity composes sub-entities -->
    <entity name="icd10cm/diagnostic_classifications" type="public" case="insensitive">
        <entries/>
        <patterns>
            <pattern>(?A:icd10cm/core_conditions)</pattern>
        </patterns>
    </entity>
</entities>
```

Key syntax:
- `<entry headword="..."/>` — flat entry (exact + substring matching)
- `<pattern>regex</pattern>` — regex pattern
- `<pattern score="0">regex</pattern>` — FP suppression (matches but returns score 0)
- `(?A:namespace/entity_name)` — cross-reference to another entity
- `type="private"` — sub-entity, not directly queryable
- `type="public"` — the top-level matchable entity
- `case="insensitive"` — case-insensitive matching

## Build Script

Your `build_entity.py` should:
- Read your core terms list from this directory
- Read from `../shared/icd10cm_terms_2026.csv` for coverage validation and gap-filling
- Output `entity.xml` in this directory
- Be deterministic (sorted outputs, no randomness)
- Print summary stats during build (core terms loaded, coverage achieved, entries generated)

## IMPORTANT: Do Not Read FP Datasets in build_entity.py

Your `build_entity.py` must NOT read `fp_dataset.json`, `fp_validation.json`, or any test dataset. FP reduction must come from **structural design**, not test-case memorization.

The adversarial validation (Layer 3) generates FPs dynamically from the entity's own vocabulary at evaluation time. It cannot be gamed by reading test files.

The only allowed inputs to `build_entity.py` are:
- Your core terms list (in this directory)
- `../shared/icd10cm_terms_2026.csv`
- `../shared/medical_conditions.xml` (for reference only)

## FP Prevention: What You Need to Know

The evaluation catches false positives through three mechanisms. The critical one is **adversarial validation**: it extracts words from your entity's own headword entries and recombines them into phrases like "glaucoma of kidney". If your entity contains both "glaucoma" and "kidney" as individually matchable terms, it will flag them.

Techniques that previous strategies used successfully:
- **Anchored regex patterns** (`^entry$`) instead of flat headwords for short entries (≤2 words). This prevents substring matching — "cholera" as a flat entry matches inside "acholera_test", but `^cholera$` only matches the exact word.
- **Avoiding single-word flat entries** entirely — they are the #1 source of word_soup FPs.
- **Multi-word entries only** — "chronic kidney disease" is safe as a flat entry; "chronic" alone is not.

Whether you need these techniques depends on what your core terms list looks like. If your terms are mostly multi-word phrases (3+ words), you may not need anchoring. If they include single medical words, you will.

## Current Status

Not yet implemented.

## Evaluation

Run the **standardized report** after any changes:
```bash
python3 ../shared/report.py entity.xml
```

This runs all 3 validation layers and produces `report.json`. Takes ~5-10 minutes.

For faster iteration during development:
```bash
# Quick dev check (layers 1-2 only, ~30s)
python3 ../shared/evaluate.py entity.xml

# Adversarial only
python3 ../shared/adversarial_validation.py entity.xml
```

## Targets

| Metric | Baseline | Target |
|--------|----------|--------|
| Coverage | 99.5% | >98% |
| Dev FP rate | 88.3% | <5% |
| Adversarial FP rate | 90.9% | <3% |
| Composite | 47.3 | >90 |

For reference, the current best scores are:
- Strategy 1 (domain-split): Composite 89.8, Coverage 100%, Adv FP 0%, Size 12,094 KB
- Strategy 3 (flat entries): Composite 90.7, Coverage 99.91%, Adv FP 0%, Size 4,566 KB

## Key Constraints

- Entity must be **self-contained** — no references to `medical_conditions.xml`
- External causes V00-Y99 are **excluded** (document this in entity comments)
- Output file must be named `entity.xml`
- Use `icd10cm/` namespace for all entity names
- The single public entity must be `icd10cm/diagnostic_classifications`
- **build_entity.py must NOT read any FP/validation dataset files**

## Iteration

1. Place your core terms list in this directory
2. Write `build_entity.py` to read core terms + ICD CSV → generate `entity.xml`
3. Run `python3 build_entity.py` to generate the entity
4. Run `python3 ../shared/report.py entity.xml` for standardized evaluation
5. Check `report.json` — focus on adversarial FP rate and coverage
6. Iterate on the builder until composite score > 90

When done, your directory should contain:
- Your core terms list file (whatever format you chose)
- `build_entity.py` — the builder script
- `entity.xml` — the generated entity (gitignored, rebuilt by builder)
- `report.json` — standardized evaluation report (gitignored, rebuilt by report.py)
