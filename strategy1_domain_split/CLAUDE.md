# Strategy 1: Domain-Split Compound Patterns

## Goal

Build an ICD-10-CM entity XML that matches official diagnostic titles using **domain-constrained compound patterns** — anatomy is split into domain-specific sub-entities so that only medically valid condition+anatomy combinations are generated.

## The Problem You're Solving

The baseline entity achieves 99.5% coverage but has an **88% false positive rate**. The root cause: compound patterns like `[condition] of [anatomy]` allow ANY condition to combine with ANY anatomy term — producing nonsense like "fracture of liver", "hernia of cornea", "cataract of knee". There are ~7M possible matches but only ~87K real titles.

## Your Strategy

Split the flat `anatomy` entity into domain-specific sub-entities and constrain which conditions can pair with each domain:

| Domain | Anatomy Examples | Valid Conditions |
|--------|-----------------|-----------------|
| `anatomy_skeletal` | femur, tibia, patella, humerus, clavicle | fracture, dislocation, stress fracture |
| `anatomy_joints` | knee, shoulder, hip joint, elbow, wrist | dislocation, subluxation, sprain, strain, arthritis |
| `anatomy_surface` | skin, hand, forearm, face, trunk, foot | burn, corrosion, abrasion, laceration, contusion |
| `anatomy_vascular` | aorta, femoral artery, portal vein | embolism, thrombosis, stenosis, occlusion |
| `anatomy_organs` | liver, kidney, lung, brain, heart | neoplasm, abscess, rupture, disease, failure |
| `anatomy_ocular` | eye, cornea, retina, lens, iris | cataract, glaucoma, retinopathy, detachment |
| `anatomy_neural` | spinal cord, brachial plexus, nerve | neuropathy, myelopathy, compression |
| `anatomy_reproductive` | uterus, ovary, cervix, testis | pregnancy conditions, prolapse |

Each domain gets its own compound pattern: `[qualifier]? [skeletal_condition] of [laterality]? [anatomy_skeletal]`

This prevents "fracture of liver" because `liver` is in `anatomy_organs`, not `anatomy_skeletal`.

## Source Data

- **CSV**: `../shared/icd10cm_terms_2026.csv` — 445K rows, 97K official titles
  - Columns: `ICD10CMCode`, `Term`, `Type`
  - Use `Type == "official"` for coverage targets
  - Exclude codes starting with V, W, X, Y (external causes)
- **Reference entity**: `../shared/medical_conditions.xml` — existing healthcare entity for architectural patterns (DO NOT modify)

## Entity XML Format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entities>
    <!-- Private sub-entity -->
    <entity name="icd10cm/anatomy_skeletal" type="private" case="insensitive">
        <entries>
            <entry headword="femur"/>
            <entry headword="tibia"/>
        </entries>
    </entity>

    <!-- Compound pattern using cross-references -->
    <entity name="icd10cm/skeletal_conditions" type="private" case="insensitive">
        <entries/>
        <patterns>
            <pattern>(?A:icd10cm/skeletal_qualifiers)\ (?A:icd10cm/condition_fracture)\ of\ (?A:icd10cm/laterality)?\ ?(?A:icd10cm/anatomy_skeletal)</pattern>
        </patterns>
    </entity>

    <!-- FP suppression -->
    <entity name="icd10cm/fp_blockers" type="private" case="insensitive">
        <entries/>
        <patterns>
            <pattern score="0">fracture of (?:liver|lung|brain|kidney)</pattern>
        </patterns>
    </entity>

    <!-- Public entity composes everything -->
    <entity name="icd10cm/diagnostic_classifications" type="public" case="insensitive">
        <entries>
            <entry headword="cholera"/>
        </entries>
        <patterns>
            <pattern>(?A:icd10cm/skeletal_conditions)</pattern>
            <pattern>(?A:icd10cm/vascular_conditions)</pattern>
        </patterns>
    </entity>
</entities>
```

Key syntax:
- `(?A:namespace/entity_name)` — cross-reference to another entity
- `score="0"` — FP suppression (matches but returns score 0)
- `type="private"` — sub-entity, not directly queryable
- `type="public"` — the top-level matchable entity
- `case="insensitive"` — case-insensitive matching
- `<!~~ comment ~~>` — XML comment style used in these entities

## Build Script

Your `build_entity.py` should:
- Read from `../shared/icd10cm_terms_2026.csv`
- Output `entity.xml` in this directory
- Be deterministic (sorted outputs, no randomness)
- Print summary stats during build

## IMPORTANT: Do Not Read FP Datasets in build_entity.py

Your `build_entity.py` must NOT read `fp_dataset.json`, `fp_validation.json`, or any test dataset. The builder should construct the entity from **structural knowledge** (which conditions pair with which anatomy domains) and the **ICD-10-CM CSV data** only.

If your builder reads the test datasets to prune entries or add suppression patterns, you are overfitting to the test set — the adversarial validation will catch this because it generates FPs dynamically from the entity's own vocabulary at evaluation time.

The only allowed inputs to `build_entity.py` are:
- `../shared/icd10cm_terms_2026.csv`
- `../shared/medical_conditions.xml` (for reference only)

## Current Status

| Metric | Score |
|--------|-------|
| Coverage | 100% (86,826/86,827) |
| Dev FP rate | 0.0% (0/171) |
| Static validation FP rate | 1.07% (7/657) |
| **Adversarial FP rate** | **0.0% (0/460)** |
| Composite | **89.8** |

All FP targets met. Composite is 89.8 — held back by file size penalty (12 MB entity = 0 size score). The builder reads only the ICD CSV — no FP dataset dependency.

### How it works

Two classes of entries use anchored regex patterns (`^entry$`) instead of flat headwords:
1. **Single-word entries** (522): "cholera", "anthrax", etc. — prevents word_soup substring FPs
2. **Short entries ≤2 words** (2,266): "stress fracture", "optic neuritis", etc. — prevents condition-prefix substring FPs

Domain-split compound patterns handle condition+anatomy matching with cross-domain prevention. FP suppression patterns block impossible combinations.

### Remaining optimization: file size

The entity is 12 MB because it includes all ~118K flat entries alongside compound patterns. The compound patterns are redundant for titles already in the flat entry set. Removing redundant flat entries covered by compound patterns could shrink the entity significantly, improving the size score.

## Evaluation

Run the **standardized report** after any changes:
```bash
python3 ../shared/report.py entity.xml
```

## Targets

| Metric | Baseline | Current | Target |
|--------|----------|---------|--------|
| Coverage | 99.5% | 100% | >98% |
| Dev FP rate | 88.3% | 0.0% | <5% |
| Adversarial FP rate | 90.9% | 0.0% | <3% |
| Composite | 47.3 | 89.8 | >90 |

## Key Constraints

- Entity must be **self-contained** — no references to `medical_conditions.xml`
- External causes V00-Y99 are **excluded** (document this in entity comments)
- Output file must be named `entity.xml`
- Use `icd10cm/` namespace for all entity names
- The single public entity must be `icd10cm/diagnostic_classifications`
- **build_entity.py must NOT read any FP/validation dataset files**

## Iteration

1. Make changes to `build_entity.py`
2. Run `python3 build_entity.py` to regenerate `entity.xml`
3. Run `python3 ../shared/report.py entity.xml` for standardized evaluation
4. Check `report.json` — focus on adversarial `word_soup` category
5. Repeat until composite score > 90

When done, your directory should contain:
- `build_entity.py` — the builder script
- `entity.xml` — the generated entity
- `report.json` — standardized evaluation report
