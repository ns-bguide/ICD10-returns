# Evaluation Methodology: ICD-10-CM Entity False Positive Testing

## 1. Context

We are building an XML entity to match ICD-10-CM diagnostic classification titles in free text. The entity is consumed by the Eduction matching engine, which uses flat headword entries (exact and substring matching) and regex-like patterns to identify medical terms.

The ICD-10-CM 2026 dataset contains 86,827 official diagnostic titles (excluding external cause codes V00–Y99). The entity must cover these titles with high accuracy while avoiding false positive matches — text that looks medical but does not correspond to any real ICD-10-CM classification.

## 2. The False Positive Problem

A naive entity that composes condition nouns (fracture, burn, embolism) with anatomy terms (femur, liver, cornea) via compound patterns like `[condition] of [anatomy]` achieves 99.5% coverage — but generates a match space of ~3.7 million possible combinations against only 86,827 real titles. This creates an effective 43:1 ratio of nonsense to real matches.

Concrete examples of false positives this produces:

- "fracture of liver" — fractures are skeletal; liver is a solid organ
- "cataract of knee" — cataracts are exclusively ocular
- "hernia of cornea" — hernias occur in body cavities, not the eye surface
- "burn of femur" — burns affect body surfaces, not internal bone

These are not edge cases. They are the dominant output of unconstrained pattern composition.

## 3. Evaluation Architecture

We evaluate entities through three independent layers, ordered by increasing resistance to overfitting.

### Layer 1: Development FP Dataset (static, hand-crafted)

**File:** `shared/fp_dataset.json` — 846 entries (600 TP, 234 FP, 12 edge cases)

Hand-crafted entries across seven false positive categories:

| Category | Count | Description |
|----------|------:|-------------|
| `impossible_combo` | 52 | Valid condition + valid anatomy, medically impossible (fracture of liver, burn of femur) |
| `domain_mismatch` | 17 | Condition applied to wrong anatomical system (cirrhosis of knee, cataract of knee) |
| `common_english` | 69 | Everyday phrases containing medical-sounding words (acute angle, viral video, chronic complainer) |
| `partial_medical` | 12 | Medical terms in non-diagnostic context (fracture clinic, infection control) |
| `ambiguous_short` | 16 | Too vague to be meaningful (chronic, left side, type 1) |
| `near_miss` | 17 | Almost-medical phrases that aren't ICD terms (bilateral happiness, chronic tiredness) |
| `nonmedical_text` | 63 | Completely unrelated non-medical text from 13 domains (news, legal, finance, tech, sports, cooking, education, weather, real estate, literature, transport, agriculture, everyday life) |

Categories 1–6 probe the boundary between medical and non-medical language — every entry contains at least one medical-adjacent word. Category 7 (`nonmedical_text`) probes the other end: full sentences with zero medical vocabulary. A well-built entity should match none of them. If it does, the entity contains overly generic terms (short prefixes, common roots) that fire on ordinary text. For example, the original entity matches "the orchestra performed beethoven ninth symphony" because "chest" (anatomy) appears as a substring inside "orchestra".

The 600 true positives are randomly sampled official ICD-10-CM titles plus 100 natural language variants (abbreviations, word reorderings).

**Purpose:** Sanity check. Validates that obvious false positives are rejected and real titles are matched. The `nonmedical_text` category additionally tests whether the entity stays silent on ordinary text with no medical content. This dataset is visible to builders during development.

**Limitation:** Static and small enough to memorize. A builder can read this file and add targeted `score="0"` patterns for each entry without solving the underlying structural problem.

### Layer 2: Static Validation Dataset (static, generated)

**File:** `shared/fp_validation.json` — 957 entries (300 TP, 657 FP)

Systematically generated entries using programmatic recombination of ICD vocabulary:

| Category | Count | Generation method |
|----------|------:|-------------------|
| `cross_domain_swap` | 200 | Take real ICD titles, swap the anatomy term to a wrong medical domain (e.g., skeletal condition → organ anatomy) |
| `random_combo` | 200 | Random condition × anatomy pairs from ICD vocabulary, verified not to be real titles |
| `template_remix` | 150 | Recombine qualifier + condition + anatomy from three different real titles |
| `novel_english` | 80 | Medical adjectives paired with non-medical nouns (different set from Layer 1) |
| `boundary_probe` | 27 | Single medical words, sentence fragments, article/qualifier additions |

All FP entries are verified against the full ICD-10-CM term set (445,315 rows, all types) to confirm they are not real titles.

**Purpose:** Tests structural correctness at scale. 200 cross-domain swaps systematically cover condition-anatomy incompatibilities that hand-crafted lists miss. Generated with seed 2026 for reproducibility.

**Limitation:** Still a static file. Builders are instructed not to read it, but can't be prevented from doing so. Both strategy builders did in fact read this file during development, which is why we added Layer 3.

### Layer 3: Adversarial Validation (dynamic, generated at eval time)

**File:** `shared/adversarial_validation.py` — generates ~740 test entries dynamically

This layer extracts vocabulary from the entity's own flat entries at evaluation time, then recombines it to generate false positives. There is no static file to memorize.

| Category | Count | Generation method |
|----------|------:|-------------------|
| `vocab_recombination` | 300 | Extracts condition and anatomy words present in the entity's headword entries, generates `[condition] of [anatomy]` phrases not found in any ICD title |
| `word_soup` | 100 | Random 2–4 word concatenations from the entity's vocabulary (≥4 char words) |
| `affix_probe` | 60 | Synthetic medical-sounding words from real prefixes/suffixes + fake roots (e.g., "hyperplaxitis", "pseudovectemia") |
| `context_injection` | 80 | Real ICD titles wrapped in clinical sentence templates ("patient denies [title]", "rule out [title]") |

The `vocab_recombination` test is the core structural probe. It asks: "Does the entity contain both the word _glaucoma_ and the word _kidney_ as matchable terms? If so, does it also match _glaucoma of kidney_?" An entity that solves the structural problem — constraining which conditions can combine with which anatomy — will score 0/300 on this test regardless of how many static FP lists were used during development.

The `word_soup` test catches a secondary problem: short flat entries (single medical words ≥5 characters) that appear as substrings in unrelated multi-word text. This is an inherent cost of flat-entry strategies and represents the current frontier of both approaches.

The `context_injection` test checks whether real titles are found inside clinical sentences. High match rates here are expected and correct — the entity should find medical terms in running text. This category is reported separately and does not count toward the FP rate.

**Purpose:** Unforgeable structural test. The entity itself is the input to FP generation, creating an adversarial feedback loop. Optimizing against this test requires actually solving the structural problem, not memorizing test cases.

## 4. Metrics

### Primary Metrics

| Metric | Definition | Measured by |
|--------|-----------|-------------|
| **Coverage** | % of 86,827 official ICD-10-CM titles matched | Exact + substring match simulation against all titles |
| **Dev FP rate** | % of 171 hand-crafted false positives matched | Layer 1 |
| **Adversarial FP rate** | % of 460 dynamic false positives matched | Layer 3 (excluding context_injection) |
| **TP rate** | % of true positive test phrases matched | Sampled from each dataset |

### Secondary Metrics

| Metric | Definition |
|--------|-----------|
| Static validation FP rate | % of 657 generated FPs matched (Layer 2) |
| Entity file size | KB of the generated XML |
| Flat entry count | Number of `<entry headword="..."/>` elements |
| Pattern count | Active patterns, reference patterns, score=0 suppression patterns |

### Composite Score

Weighted combination used for strategy comparison:

```
Composite = Coverage × 0.35
          + (100 − Dev FP rate) × 0.15
          + (100 − Static Val FP rate) × 0.15
          + (100 − Adversarial FP rate) × 0.25
          + Size score × 0.10
```

Size score = max(0, 100 − file_size_KB / 50). This applies a gentle penalty for large entities — 1 point per 50 KB.

The adversarial FP rate carries the highest single weight (25%) because it is the only metric that cannot be gamed by reading test files.

### Match Simulation

The evaluator does not run the real Eduction engine. It simulates matching with two mechanisms:

1. **Exact match:** The test phrase (lowered, stripped) is compared against the set of all entity headwords. Match if identical.
2. **Substring match:** For each headword ≥5 characters, check if it appears as a substring in the test phrase. Match if found.

Regex patterns in the entity are evaluated directly via Python `re.search`.

This simulation approximates the Eduction engine's behavior for flat entries and simple patterns. It does not handle cross-entity references (`(?A:...)` patterns), which are treated as opaque. The approximation is conservative for FP testing: if the simulation doesn't match a false positive, the real engine likely won't either, since the simulation is more permissive (substring matching is broader than Eduction's phrase-boundary-aware matching).

## 5. Builder Constraints

Strategy builders are given these rules:

1. `build_entity.py` may only read `icd10cm_terms_2026.csv` and optionally `medical_conditions.xml` (as architectural reference)
2. `build_entity.py` must NOT read `fp_dataset.json`, `fp_validation.json`, or any evaluation dataset
3. FP reduction must come from structural design (domain constraints, entry selection) not test-case memorization
4. Evaluation is performed by running `python3 ../shared/report.py entity.xml`, which produces a standardized `report.json`

Constraint 2 is enforced by convention, not code. However, constraint violations are caught by the adversarial layer: a builder that prunes entries based on static FP lists will still fail on dynamically generated FPs derived from its remaining vocabulary.

## 6. Results

### Baseline (unconstrained compound patterns)

| Metric | Value |
|--------|-------|
| Coverage | 99.48% (86,373 / 86,827) |
| Dev FP rate | 88.3% (151 / 171) |
| Static validation FP rate | 98.0% (644 / 657) |
| Adversarial FP rate | 90.9% (418 / 460) |
| Adversarial vocab_recombination | 290 / 300 |
| Entity size | 936 KB, 14,085 entries, 67 patterns |
| **Composite** | **47.3** |

The baseline matches nearly everything — including nearly all false positives. The adversarial vocab_recombination rate of 97% confirms the structural problem: almost any condition × anatomy combination the entity can construct will be matched, whether or not it is a real ICD title.

### Strategy 1: Domain-Split Compound Patterns

| Metric | Value |
|--------|-------|
| Coverage | 100.0% (86,826 / 86,827) |
| Dev FP rate | 0.0% (0 / 171) |
| Static validation FP rate | 1.07% (7 / 657) |
| Adversarial FP rate | 0.0% (0 / 460) |
| Adversarial vocab_recombination | 0 / 300 |
| Adversarial word_soup | 0 / 100 |
| Entity size | 12,094 KB, 115,698 entries, 2,807 patterns |
| **Composite** | **89.8** |

Domain-split fully solves both the structural combination problem (0/300 vocab_recombination) and the word_soup problem (0/100). Single-word and ≤2-word entries use anchored regex patterns (`^entry$`) instead of flat headwords, preventing substring matches. The 7 remaining static validation FPs are 3+ word entries that substring-match into borderline cases. Entity size is large (12 MB) due to including all titles as flat entries alongside domain-constrained patterns — the size penalty is the main drag on composite score.

### Strategy 3: Flat Entries Only

| Metric | Value |
|--------|-------|
| Coverage | 99.91% (86,751 / 86,827) |
| Dev FP rate | 0.0% (0 / 171) |
| Static validation FP rate | 1.07% (7 / 657) |
| Adversarial FP rate | 0.0% (0 / 460) |
| Adversarial vocab_recombination | 0 / 300 |
| Adversarial word_soup | 0 / 100 |
| Entity size | 4,566 KB, 52,516 entries, 2,784 patterns |
| **Composite** | **90.7** |

Flat entries also fully solve both the structural combination and word_soup problems. The same anchored-pattern technique prevents short entries from substring-matching into unrelated text. The entity is smaller (4.6 MB) and the higher composite score reflects the size advantage. Neither builder reads any FP test dataset — all FP prevention comes from structural entry classification derived from the ICD title set itself.

## 7. What Each Layer Catches

| False positive type | Layer 1 (Dev) | Layer 2 (Static) | Layer 3 (Adversarial) |
|---|---|---|---|
| Impossible anatomy combos (fracture of liver) | Yes | Yes | Yes |
| Domain-mismatch combos (cataract of knee) | Yes | Yes | Yes |
| Common English phrases (viral video) | Yes | Yes | No (not tested) |
| Non-medical text with no medical words | **Yes** | No | No |
| Random condition × anatomy from ICD vocab | No | Yes | Yes |
| Recombined qualifier + condition + anatomy | No | Yes | No (tested differently) |
| Vocabulary extracted from the entity itself | No | No | **Yes** |
| Short entries as substrings in word jumble | No | No | **Yes** |
| Synthetic medical-sounding nonwords | No | No | **Yes** |

The critical diagonal: Layer 3 is the only layer that tests whether the entity's own vocabulary creates false positives. Layers 1 and 2 test against a fixed universe of phrases. Layer 3 adapts to whatever vocabulary the entity contains.

The `nonmedical_text` category in Layer 1 fills a distinct gap: it tests whether the entity fires on ordinary text that has no medical content at all. Categories 1–6 contain at least one medical-adjacent word; category 7 contains none. This catches overly generic entries (short prefixes, anatomical roots) that substring-match into unrelated words.

## 8. Known Limitations

1. **Simulation vs. real engine.** The evaluator uses substring matching, which is more permissive than Eduction's phrase-boundary matching. Some FPs flagged here may not occur in production. This makes our FP rates conservative upper bounds.

2. **Context injection ambiguity.** "Patient denies fracture of femur" contains "fracture of femur" — a real ICD title. The evaluator counts this as a match, and both strategies match 80/80 context injections. Whether this is a true or false positive depends on the downstream application. We report it separately and exclude it from FP rate calculations.

3. **Word soup is inherent to substring matching.** Any entity with flat entries ≥5 characters will match some random word concatenations via substring. This is a property of the matching model, not a flaw in the entity. The word_soup test quantifies this irreducible cost.

4. **No enriched term testing.** The CSV contains 445,315 terms including enriched variants from SNOMED, MeSH, MEDCIN, and other vocabularies. Our coverage metric only tests against the 86,827 official titles. Enriched term coverage is a separate concern.

5. **Static datasets can be leaked.** Builder constraint #2 (don't read FP files) is enforced by convention. Both strategy builders did read `fp_validation.json` during early development, which is why the adversarial layer was added. The adversarial layer is unforgeable by design.

## 9. Tooling

All evaluation code is in `shared/`:

| File | Purpose |
|------|---------|
| `evaluate.py` | Core evaluation: coverage, dev FP, static validation |
| `fp_dataset.py` | Generates `fp_dataset.json` (Layer 1) |
| `fp_validation.py` | Generates `fp_validation.json` (Layer 2) |
| `adversarial_validation.py` | Dynamic adversarial generation and evaluation (Layer 3) |
| `report.py` | Standardized report combining all layers |
| `compare.py` | Side-by-side comparison of multiple strategy results |

### Running evaluation

```bash
# Full standardized report (all layers)
python3 shared/report.py <entity.xml>

# Quick development check (layers 1-2 only)
python3 shared/evaluate.py <entity.xml>

# Adversarial only
python3 shared/adversarial_validation.py <entity.xml>

# Compare all strategies
python3 shared/compare.py
```
