# Strategy 3: Flat Entries Only (No Compound Patterns)

## Goal

Build an ICD-10-CM entity XML that matches official diagnostic titles using **explicit flat entries only** — every matchable phrase is listed individually. No compound `condition × anatomy` patterns that generate combinatorial explosions.

## The Problem You're Solving

The baseline entity achieves 99.5% coverage but has an **88% false positive rate**. The root cause: compound patterns like `[condition] of [anatomy]` allow ANY condition to combine with ANY anatomy term — producing nonsense like "fracture of liver", "hernia of cornea", "cataract of knee". There are ~7M possible matches but only ~87K real titles.

## Your Strategy

Abandon compound patterns entirely. Instead:

1. **Extract every official ICD-10-CM title** directly as a flat `<entry headword="..."/>`
2. **Generate natural language variants** (abbreviations, reorderings) as additional flat entries
3. **Factor encounter suffixes** to reduce entry count without losing coverage
4. **No condition × anatomy patterns** — this is the core of the strategy

This guarantees zero false positives from combinatorial explosion — you can only match what's explicitly listed.

## Source Data

- **CSV**: `../shared/icd10cm_terms_2026.csv` — 445K rows, 97K official titles
  - Columns: `ICD10CMCode`, `Term`, `Type`
  - Use `Type == "official"` for the core flat entries (~86,827 excluding V-Y)
  - Exclude codes starting with V, W, X, Y (external causes)
- **Reference entity**: `../shared/medical_conditions.xml` — existing healthcare entity for architectural patterns (DO NOT modify)

## Entity XML Format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entities>
    <!-- Chapter sub-entity -->
    <entity name="icd10cm/chapter_A" type="private" case="insensitive">
        <entries>
            <entry headword="cholera"/>
            <entry headword="typhoid fever"/>
        </entries>
    </entity>

    <!-- Variants -->
    <entity name="icd10cm/variants" type="private" case="insensitive">
        <entries>
            <entry headword="lt femur fracture"/>
        </entries>
    </entity>

    <!-- Public entity composes chapter sub-entities -->
    <entity name="icd10cm/diagnostic_classifications" type="public" case="insensitive">
        <entries/>
        <patterns>
            <pattern>(?A:icd10cm/chapter_A)</pattern>
            <pattern>(?A:icd10cm/variants)</pattern>
        </patterns>
    </entity>
</entities>
```

Key syntax:
- `<entry headword="..."/>` — exact flat entry
- `score="0"` — FP suppression (matches but returns score 0)
- `type="private"` — sub-entity, not directly queryable
- `type="public"` — the top-level matchable entity
- `case="insensitive"` — case-insensitive matching
- `(?A:namespace/entity_name)` — cross-reference to another entity
- `<!~~ comment ~~>` — XML comment style used in these entities

## Build Script

Your `build_entity.py` should:
- Read from `../shared/icd10cm_terms_2026.csv`
- Output `entity.xml` in this directory
- Be deterministic (sorted outputs, no randomness)
- Print summary stats during build

## IMPORTANT: Do Not Read FP Datasets in build_entity.py

Your `build_entity.py` must NOT read `fp_dataset.json`, `fp_validation.json`, or any test dataset. The builder should construct the entity from the **ICD-10-CM CSV data** only.

If your builder reads the test datasets to prune entries or add suppression patterns, you are overfitting to the test set — the adversarial validation will catch this because it generates FPs dynamically from the entity's own vocabulary at evaluation time.

The only allowed inputs to `build_entity.py` are:
- `../shared/icd10cm_terms_2026.csv`
- `../shared/medical_conditions.xml` (for reference only)

## Current Status

| Metric | Score |
|--------|-------|
| Coverage | 99.91% (76 uncovered) |
| Dev FP rate | 0.0% (0/171) |
| Static validation FP rate | 1.07% (7/657) |
| **Adversarial FP rate** | **0.0% (0/460)** |
| Composite | **90.7** |

All targets met. The builder reads only the ICD CSV — no FP dataset dependency.

### How it works

Two classes of entries use anchored regex patterns (`^entry$`) instead of flat headwords:
1. **Single-word entries** (522): "cholera", "anthrax", etc. — prevents word_soup substring FPs
2. **Short entries ≤2 words** (2,262): "stress fracture", "optic neuritis", etc. — prevents condition-prefix substring FPs like "stress fracture of heart"

Both classes are identified structurally from the ICD title set — no FP test data involved.

### Remaining 7 static validation FPs

All are 3+ word flat entries substring-matching into longer phrases. Most are borderline true positives:
- "traumatic laceration of stomach" (contains real title "laceration of stomach")
- "mild contusion of knee" (contains real title "contusion of knee")
- "diagnosed with type 2 diabetes mellitus" (context injection)

These represent the irreducible floor of flat-entry substring matching.

## Evaluation

Run the **standardized report** after any changes:
```bash
python3 ../shared/report.py entity.xml
```

## Targets (all met)

| Metric | Baseline | Current | Target |
|--------|----------|---------|--------|
| Coverage | 99.5% | 99.91% | >99.5% |
| Dev FP rate | 88.3% | 0.0% | <5% |
| Adversarial FP rate | 90.9% | 0.0% | <3% |
| Composite | 47.3 | **90.7** | >90 |

## Key Constraints

- Entity must be **self-contained** — no references to `medical_conditions.xml`
- External causes V00-Y99 are **excluded** (document this in entity comments)
- **No compound condition × anatomy patterns** — this is the whole point of this strategy
- Output file must be named `entity.xml`
- Use `icd10cm/` namespace for all entity names
- The single public entity must be `icd10cm/diagnostic_classifications`
- **build_entity.py must NOT read any FP/validation dataset files**

## Iteration

1. Make changes to `build_entity.py`
2. Run `python3 build_entity.py` to regenerate `entity.xml`
3. Run `python3 ../shared/report.py entity.xml` for standardized evaluation
4. Check `report.json` — focus on adversarial `word_soup` category and coverage gaps
5. Repeat until composite score > 90

When done, your directory should contain:
- `build_entity.py` — the builder script
- `entity.xml` — the generated entity
- `report.json` — standardized evaluation report
