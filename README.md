# ICD-10-CM Entity Evaluation

This project builds and evaluates XML entities that match ICD-10-CM diagnostic classification titles in free text. Multiple strategies are compared using a 3-layer validation pipeline that measures coverage (do we match real titles?) and false positive rates (do we match nonsense?).

## Background

The ICD-10-CM 2026 dataset has **86,827 official diagnostic titles**. A naive entity that composes condition nouns with anatomy terms produces ~3.7M possible matches — a 43:1 ratio of nonsense to real titles. The challenge is matching real titles without matching "fracture of liver" or "cataract of knee".

Three strategies already exist in this repo. **Your task is to build a fourth** using your own core terms list.

### Current results

| Strategy | Coverage | False Positive Rate | Composite Score |
|----------|----------|---------------------|-----------------|
| Original (`medical_conditions.xml`) | 92.15% | 89.1% | 48.3 |
| Baseline (unconstrained patterns) | 99.48% | 90.9% | 47.3 |
| Strategy 1 — Domain-split patterns | 100% | 0% | 89.8 |
| Strategy 3 — Flat entries only | 99.91% | 0% | 90.7 |
| **Strategy 4 — Core terms** | — | — | **Target: >90** |

## Prerequisites

- **Python 3.8+** (stdlib only — no pip install needed)
- **VS Code** with the [Claude Code extension](https://marketplace.visualstudio.com/items?itemName=anthropics.claude-code)
- Your **core terms list** file (the curated medical vocabulary you've already prepared)

## Quick Start

### 1. Clone and open

```bash
git clone <repo-url>
cd ICD10-returns
code .
```

### 2. Add your core terms file

Copy your core terms list into the `strategy4_core_terms/` directory:

```
strategy4_core_terms/
├── CLAUDE.md            ← Claude reads this automatically
├── your_terms.csv       ← PUT YOUR FILE HERE (any name, any format)
├── build_entity.py      ← Claude will create this
└── entity.xml           ← generated output
```

The file can be any format — CSV, JSON, plain text with one term per line — Claude will read it and adapt.

### 3. Open Claude Code in VS Code

Open the Claude Code panel in VS Code (Cmd+Shift+P → "Claude Code: Open" or click the Claude icon in the sidebar). Claude will automatically read the `CLAUDE.md` files which contain all project instructions, constraints, and evaluation details.

Then tell Claude:

> Build Strategy 4 using my core terms list in strategy4_core_terms/your_terms.csv

Claude will:
1. Read your core terms file and the ICD-10-CM CSV
2. Write `build_entity.py` that combines them into an entity XML
3. Run the builder to generate `entity.xml`
4. Run the evaluation pipeline (`python3 ../shared/report.py entity.xml`)
5. Iterate on the builder until the composite score target is met

### 4. Review results

After evaluation, results appear in two places:

**Terminal output** — the report prints a summary:
```
─── COVERAGE ──────────────────────────────────────────────────────
  Official titles:        86,827
  Covered:                85,200  (98.13%)

─── FALSE POSITIVE RATES ──────────────────────────────────────────
  Dev (hand-crafted)          0.0%        0/171     98.3%
  Static validation           1.2%        8/657     96.0%
  Adversarial (dynamic)       0.4%        2/460     95.0%

─── COMPOSITE SCORE ───────────────────────────────────────────────
  COMPOSITE:              91.2
```

**`report.json`** — full structured results with per-category breakdowns, per-chapter coverage, matched/missed entries, and composite score components. This file is generated in `strategy4_core_terms/report.json`.

**Compare against all strategies:**
```bash
python3 shared/compare.py
```
This prints a side-by-side table of all strategies that have been evaluated.

**Visual report** — open `EVALUATION_REPORT.html` in a browser to see the existing comparison with charts and detailed analysis.

## How Evaluation Works

The entity is tested against three independent layers:

| Layer | What it tests | Size | Can be gamed? |
|-------|---------------|------|---------------|
| **1. Dev FP** | Hand-crafted false positives ("fracture of liver", "viral video") | 171 FP | Yes — visible during development |
| **2. Static Validation** | Programmatically generated FPs (cross-domain swaps, random combos) | 657 FP | Technically yes — static file |
| **3. Adversarial** | Extracts vocabulary from **your entity** and recombines it into FPs | 460 FP | **No** — generated at eval time |

Layer 3 is the one that matters. If your entity has "glaucoma" and "kidney" as individually matchable terms, it will test "glaucoma of kidney". You can't game it by reading test files — it adapts to whatever your entity contains.

**Composite score** (target >90):
```
Coverage × 0.35 + (100 − Dev FP%) × 0.15 + (100 − Val FP%) × 0.15 + (100 − Adv FP%) × 0.25 + Size × 0.10
```

## Project Structure

```
ICD10-returns/
├── README.md                       ← You are here
├── CLAUDE.md                       # Instructions for Claude Code (read automatically)
├── EVALUATION_METHODOLOGY.md       # Detailed evaluation methodology
├── EVALUATION_REPORT.html          # Visual comparison report (open in browser)
│
├── icd10cm_terms_2026.csv          # ICD-10-CM 2026 dataset (445K rows)
├── medical_conditions.xml          # Original healthcare entity (reference)
│
├── shared/                         # Evaluation framework — DO NOT MODIFY
│   ├── report.py                   #   Full 3-layer evaluation
│   ├── evaluate.py                 #   Coverage + layers 1-2
│   ├── adversarial_validation.py   #   Layer 3 (dynamic)
│   ├── compare.py                  #   Side-by-side comparison
│   ├── fp_dataset.json             #   Layer 1 test data
│   └── fp_validation.json          #   Layer 2 test data
│
├── baseline/                       # Reference: unconstrained patterns (FP rate ~90%)
├── original/                       # Reference: wrapped medical_conditions.xml
├── strategy1_domain_split/         # Domain-constrained compound patterns
├── strategy3_flat_entries/         # Explicit flat entries for all titles
│
└── strategy4_core_terms/           # YOUR STRATEGY
    ├── CLAUDE.md                   #   Strategy instructions (Claude reads this)
    ├── <your_core_terms_file>      #   Your input — place it here
    ├── build_entity.py             #   Builder — Claude creates this
    └── entity.xml                  #   Output — generated, gitignored
```

## Rules

- `build_entity.py` reads your core terms list + `icd10cm_terms_2026.csv` only
- `build_entity.py` must **not** read any file from `shared/` except the CSV and `medical_conditions.xml`
- All FP prevention must be structural — no test-file memorization
- The entity's public name must be `icd10cm/diagnostic_classifications`
- External causes (V00–Y99) are excluded
- Don't modify anything in `shared/` or other strategy directories

## Common Commands

```bash
# Build the entity
cd strategy4_core_terms
python3 build_entity.py

# Full evaluation (all 3 layers, ~5-10 min)
python3 ../shared/report.py entity.xml

# Quick check (layers 1-2 only, ~30s)
python3 ../shared/evaluate.py entity.xml

# Compare all strategies
cd ..
python3 shared/compare.py
```

## Regenerating Existing Strategies

The generated `entity.xml` files are gitignored. To regenerate them:

```bash
# Baseline
cd baseline && python3 build_entity.py && cd ..

# Strategy 1
cd strategy1_domain_split && python3 build_entity.py && cd ..

# Strategy 3
cd strategy3_flat_entries && python3 build_entity.py && cd ..

# Original (wraps medical_conditions.xml)
cd original && python3 build_wrapper.py && cd ..
```
