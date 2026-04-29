# ICD-10-CM Entity Builder — Project Guide

## What This Project Is

This project builds and evaluates XML entities that match ICD-10-CM diagnostic classification titles in free text. The entities are consumed by the Eduction matching engine, which uses flat headword entries and regex patterns.

The ICD-10-CM 2026 dataset contains **86,827 official diagnostic titles** (excluding external cause codes V00–Y99). The challenge: achieve high coverage of these titles while avoiding false positives — text that looks medical but doesn't correspond to any real ICD-10-CM classification.

## Project Structure

```
ICD10-returns/
├── CLAUDE.md                       ← You are here
├── EVALUATION_METHODOLOGY.md       # Detailed evaluation methodology
├── EVALUATION_REPORT.html          # Visual comparison of all strategies
│
├── icd10cm_terms_2026.csv          # ICD-10-CM 2026 terms (445K rows, source data)
├── medical_conditions.xml          # Original healthcare entity (reference)
│
├── shared/                         # Evaluation framework (DO NOT MODIFY)
│   ├── evaluate.py                 #   Coverage + dev FP + static validation
│   ├── adversarial_validation.py   #   Dynamic adversarial FP generation
│   ├── report.py                   #   Standardized report (runs all layers)
│   ├── compare.py                  #   Side-by-side comparison
│   ├── fp_dataset.json             #   Layer 1: 783 hand-crafted test entries
│   ├── fp_dataset.py               #   Generator for fp_dataset.json
│   ├── fp_validation.json          #   Layer 2: 957 generated test entries
│   ├── fp_validation.py            #   Generator for fp_validation.json
│   ├── icd10cm_terms_2026.csv      #   → symlink to ../icd10cm_terms_2026.csv
│   └── medical_conditions.xml      #   → symlink to ../medical_conditions.xml
│
├── baseline/                       # Baseline entity (unconstrained patterns)
│   ├── build_entity.py             #   Builder script
│   ├── entity.xml                  #   Generated entity
│   └── ...
│
├── original/                       # Wrapped medical_conditions.xml
│   ├── build_wrapper.py            #   Wrapper script
│   └── entity.xml                  #   Generated wrapped entity
│
├── strategy1_domain_split/         # Strategy 1: domain-constrained patterns
│   ├── CLAUDE.md                   #   Strategy-specific instructions
│   ├── build_entity.py             #   Builder script
│   └── entity.xml                  #   Generated entity (gitignored)
│
├── strategy3_flat_entries/         # Strategy 3: explicit flat entries only
│   ├── CLAUDE.md                   #   Strategy-specific instructions
│   ├── build_entity.py             #   Builder script
│   └── entity.xml                  #   Generated entity (gitignored)
│
└── strategy4_core_terms/           # Strategy 4: core terms (YOUR TASK)
    ├── CLAUDE.md                   #   ← Start here for strategy instructions
    ├── <your_core_terms_file>      #   Your pre-existing core terms list (you bring this)
    ├── build_entity.py             #   You will create this
    └── entity.xml                  #   Generated entity (gitignored)
```

## Quick Start — Strategy 4: Core Terms

You are here to build an entity from your **pre-existing core terms list**. Follow these steps:

### 1. Read the strategy brief
```
Read strategy4_core_terms/CLAUDE.md
```
This explains the entity format, builder constraints, FP prevention techniques, and evaluation targets.

### 2. Understand the evaluation system
```
Read EVALUATION_METHODOLOGY.md
```
Three validation layers, each harder to game. Layer 3 (adversarial) generates FPs from your entity's own vocabulary — it's the one that matters most.

### 3. Place your core terms list
Copy your core terms file into `strategy4_core_terms/`. It can be any format (text, CSV, JSON) — your builder just needs to read it.

### 4. Study the ICD-10-CM data
```bash
# The CSV your builder will cross-reference against
head -5 icd10cm_terms_2026.csv
# Columns: ICD10CMCode, Term, Type
# Use Type == "official", exclude codes starting with V, W, X, Y (86,827 titles)
```

### 5. Study existing strategies (for reference)
```
Read strategy1_domain_split/CLAUDE.md    # Domain-split compound patterns
Read strategy3_flat_entries/CLAUDE.md     # Explicit flat entries for every title
```
Your approach should be structurally different from both.

### 6. Build and evaluate
```bash
cd strategy4_core_terms
python3 build_entity.py                   # Generate entity.xml from core terms + CSV
python3 ../shared/report.py entity.xml    # Run all 3 validation layers (~5-10 min)
```

### 7. Compare against other strategies
```bash
python3 shared/compare.py
```

## Rules

### Builder constraints
1. `build_entity.py` may read: `../shared/icd10cm_terms_2026.csv`, your own core terms list (in your strategy directory), and optionally `../shared/medical_conditions.xml` (as architectural reference)
2. `build_entity.py` must **NOT** read `fp_dataset.json`, `fp_validation.json`, or any evaluation dataset
3. FP reduction must come from **structural design**, not test-case memorization
4. The adversarial layer (Layer 3) generates FPs dynamically from the entity's own vocabulary — it cannot be gamed

### Entity constraints
- The public entity must be named `icd10cm/diagnostic_classifications`
- Use `icd10cm/` namespace for all entity names
- `case="insensitive"` on all entities
- External causes V00–Y99 are excluded
- Entity must be self-contained (no cross-references to `medical_conditions.xml`)

### Do not modify
- Anything in `shared/` — the evaluation framework is shared across all strategies
- Other strategy directories — each strategy stands on its own
- `icd10cm_terms_2026.csv` and `medical_conditions.xml` — source data

## Evaluation System

Three independent validation layers, each harder to game than the last:

| Layer | File | FP tests | Can be memorized? |
|-------|------|----------|-------------------|
| 1. Dev FP | `shared/fp_dataset.json` | 171 | Yes (visible) |
| 2. Static Validation | `shared/fp_validation.json` | 657 | Technically yes |
| 3. Adversarial | Generated at eval time | 460 | **No** (dynamic) |

**Layer 3 is the one that matters.** It extracts vocabulary from your entity's own headwords and recombines it to generate false positives. If your entity contains "glaucoma" and "kidney" as matchable terms, it will test "glaucoma of kidney". The only way to pass is to actually solve the structural problem.

### Composite score formula
```
Composite = Coverage × 0.35
          + (100 − Dev FP rate) × 0.15
          + (100 − Static Val FP rate) × 0.15
          + (100 − Adversarial FP rate) × 0.25
          + Size score × 0.10

Size score = max(0, 100 − file_size_KB / 50)
```

### Target: Composite > 90

Current standings:

| Strategy | Coverage | Adv FP | Composite |
|----------|----------|--------|-----------|
| Original (medical_conditions.xml) | 92.15% | 89.1% | 48.3 |
| Baseline (unconstrained) | 99.48% | 90.9% | 47.3 |
| Strategy 1 (domain-split) | 100% | 0% | 89.8 |
| Strategy 3 (flat entries) | 99.91% | 0% | 90.7 |

## Common Commands

```bash
# Build an entity
cd strategy4_core_terms && python3 build_entity.py

# Full evaluation (all 3 layers, ~5-10 min)
python3 ../shared/report.py entity.xml

# Quick dev check (layers 1-2 only, ~30s)
python3 ../shared/evaluate.py entity.xml

# Adversarial only
python3 ../shared/adversarial_validation.py entity.xml

# Compare all strategies
python3 shared/compare.py
```

## Key Insight: Why FP Prevention Is Hard

A naive entity that matches "fracture" + "of" + "[any anatomy]" produces 3.7M combinations but only 87K are real titles — a 43:1 false-to-real ratio. The structural challenge is ensuring that only medically valid combinations match. See `EVALUATION_METHODOLOGY.md` for the full analysis.
