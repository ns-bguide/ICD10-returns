"""Generate a HELD-OUT validation dataset for false positive testing.

This dataset is NOT meant to be seen by strategy builders during development.
It tests whether strategies solve the STRUCTURAL problem (constraining what
can combine with what) vs. just memorizing the known FP test cases.

Generation approach:
  1. CROSS_DOMAIN_SWAP: Take real ICD title "X of Y", swap Y to a wrong-domain
     anatomy. E.g., "fracture of femur" -> "fracture of liver"
  2. RANDOM_COMBO: Random condition × anatomy from ICD vocabulary that aren't
     real titles. Tests combinatorial coverage.
  3. TEMPLATE_REMIX: Recombine qualifiers + conditions + anatomies from different
     real titles into plausible-looking but nonexistent combos.
  4. NOVEL_ENGLISH: Programmatically generated common-English phrases using
     medical adjectives/nouns in non-medical contexts (NOT the same phrases
     as fp_dataset.py).
  5. BOUNDARY_PROBE: Phrases designed to test specific boundary decisions —
     single medical words, partial matches, near-homonyms.

Each entry is verified NOT to be an actual ICD-10-CM official title.

Usage:
    python3 fp_validation.py
"""

import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

random.seed(2026)

CSV_PATH = Path(__file__).parent / "icd10cm_terms_2026.csv"
OUTPUT_PATH = Path(__file__).parent / "fp_validation.json"
EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")


def load_all_titles() -> Set[str]:
    """Load all official ICD-10-CM titles as lowercase set."""
    titles = set()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Type"] == "official" and not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                titles.add(row["Term"].strip().lower())
    return titles


def load_all_terms() -> Set[str]:
    """Load ALL terms (official + enriched) as lowercase set for broader exclusion."""
    terms = set()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                terms.add(row["Term"].strip().lower())
    return terms


# ── Anatomy domains (for cross-domain swapping) ─────────────────────
# These represent medically disjoint domains. A condition valid in one
# domain is typically nonsensical in another.

DOMAIN_SKELETAL = [
    "femur", "tibia", "fibula", "patella", "humerus", "radius", "ulna",
    "clavicle", "scapula", "sternum", "rib", "pelvis", "sacrum",
    "calcaneus", "talus", "metacarpal bone", "metatarsal",
]

DOMAIN_JOINTS = [
    "knee joint", "hip joint", "shoulder joint", "ankle joint",
    "elbow joint", "wrist", "sacroiliac joint",
    "acromioclavicular joint", "temporomandibular joint",
]

DOMAIN_ORGANS = [
    "liver", "kidney", "lung", "brain", "heart", "spleen", "pancreas",
    "stomach", "gallbladder", "bladder", "esophagus", "appendix",
    "thyroid gland", "adrenal gland",
]

DOMAIN_SURFACE = [
    "skin", "scalp", "face", "trunk", "palm", "buttock", "groin",
    "axilla", "perineum", "abdominal wall", "chest wall",
]

DOMAIN_OCULAR = [
    "cornea", "retina", "lens", "iris", "sclera", "choroid",
    "conjunctiva", "optic nerve", "vitreous body", "macula",
]

DOMAIN_VASCULAR = [
    "aorta", "carotid artery", "femoral artery", "pulmonary artery",
    "coronary artery", "portal vein", "jugular vein", "renal artery",
]

DOMAIN_NEURAL = [
    "spinal cord", "brachial plexus", "sciatic nerve", "median nerve",
    "facial nerve", "trigeminal nerve", "ulnar nerve",
]

DOMAIN_REPRODUCTIVE = [
    "uterus", "ovary", "cervix", "fallopian tube", "vagina",
    "prostate", "testis", "epididymis",
]

ALL_DOMAINS = {
    "skeletal": DOMAIN_SKELETAL,
    "joints": DOMAIN_JOINTS,
    "organs": DOMAIN_ORGANS,
    "surface": DOMAIN_SURFACE,
    "ocular": DOMAIN_OCULAR,
    "vascular": DOMAIN_VASCULAR,
    "neural": DOMAIN_NEURAL,
    "reproductive": DOMAIN_REPRODUCTIVE,
}

# Conditions restricted to specific domains
DOMAIN_RESTRICTED_CONDITIONS = {
    "skeletal": [
        "fracture", "displaced fracture", "nondisplaced fracture",
        "stress fracture", "pathological fracture", "greenstick fracture",
        "torus fracture", "comminuted fracture", "spiral fracture",
        "transverse fracture", "oblique fracture", "segmental fracture",
        "osteomyelitis", "osteonecrosis", "osteolysis",
    ],
    "joints": [
        "dislocation", "subluxation", "sprain", "strain",
        "unspecified dislocation", "unspecified subluxation",
        "recurrent dislocation", "recurrent subluxation",
        "arthropathy", "osteoarthritis",
    ],
    "surface": [
        "burn", "corrosion", "abrasion", "blister",
        "first degree burn", "second degree burn", "third degree burn",
        "erythema", "sunburn",
    ],
    "ocular": [
        "cataract", "glaucoma", "retinopathy", "keratitis",
        "conjunctivitis", "uveitis", "retinal detachment",
        "macular degeneration", "optic neuritis",
    ],
    "vascular": [
        "embolism", "thrombosis", "aneurysm",
        "atherosclerosis", "arteritis", "phlebitis",
        "varicose veins",
    ],
    "neural": [
        "neuropathy", "myelopathy", "radiculopathy",
        "neuralgia", "nerve compression",
    ],
    "reproductive": [
        "ectopic pregnancy", "endometriosis",
        "prolapse", "vaginitis",
    ],
}


# ── Generators ───────────────────────────────────────────────────────

def gen_cross_domain_swaps(all_titles: Set[str], n=200) -> List[dict]:
    """Take domain-restricted conditions, pair with wrong-domain anatomy."""
    entries = []
    seen = set()

    for source_domain, conditions in DOMAIN_RESTRICTED_CONDITIONS.items():
        # Target domains are everything EXCEPT the source
        wrong_domains = {k: v for k, v in ALL_DOMAINS.items() if k != source_domain}

        for cond in conditions:
            for target_domain, anatomies in wrong_domains.items():
                for anat in anatomies:
                    phrase = f"{cond} of {anat}"
                    if phrase in all_titles or phrase in seen:
                        continue
                    seen.add(phrase)
                    entries.append({
                        "text": phrase,
                        "label": "FP",
                        "category": "cross_domain_swap",
                        "source_domain": source_domain,
                        "target_domain": target_domain,
                        "reason": f"{cond} is {source_domain}-domain; {anat} is {target_domain}-domain",
                    })

    random.shuffle(entries)
    return entries[:n]


def gen_random_combos(all_titles: Set[str], all_terms: Set[str], n=200) -> List[dict]:
    """Random condition × anatomy pairings from ICD vocabulary that aren't real."""
    of_pat = re.compile(r"^(.+?)\s+of\s+(.+?)$")

    conditions = set()
    anatomies = set()
    for t in all_titles:
        t2 = re.sub(r",\s*(initial|subsequent)\s+encounter.*$", "", t)
        t2 = re.sub(r",\s*sequela.*$", "", t2)
        t2 = re.sub(r",\s*(right|left|bilateral|unspecified)\s*$", "", t2)
        m = of_pat.match(t2)
        if m:
            c = m.group(1).strip()
            a = m.group(2).strip()
            if 1 <= len(c.split()) <= 4 and 1 <= len(a.split()) <= 3:
                conditions.add(c)
                anatomies.add(a)

    conditions = sorted(conditions)
    anatomies = sorted(anatomies)
    entries = []
    seen = set()
    attempts = 0

    while len(entries) < n and attempts < n * 20:
        attempts += 1
        c = random.choice(conditions)
        a = random.choice(anatomies)
        phrase = f"{c} of {a}"
        if phrase in all_titles or phrase in all_terms or phrase in seen:
            continue
        seen.add(phrase)
        entries.append({
            "text": phrase,
            "label": "FP",
            "category": "random_combo",
            "reason": f"random pairing: '{c}' + '{a}' not in ICD-10-CM",
        })

    return entries


def gen_template_remix(all_titles: Set[str], n=150) -> List[dict]:
    """Recombine qualifiers + conditions + anatomies from different real titles."""
    qualifiers = [
        "displaced", "nondisplaced", "complete", "incomplete",
        "partial", "open", "closed", "traumatic", "nontraumatic",
        "pathological", "stress", "chronic", "acute", "recurrent",
        "malignant", "benign", "primary", "secondary",
        "superficial", "deep", "spontaneous",
    ]

    conditions = [
        "fracture", "dislocation", "subluxation", "laceration", "contusion",
        "sprain", "strain", "burn", "corrosion", "hernia", "prolapse",
        "stenosis", "occlusion", "embolism", "thrombosis", "rupture",
        "abscess", "ulcer", "neoplasm", "cyst", "polyp", "fistula",
        "gangrene", "necrosis", "hemorrhage", "edema", "effusion",
        "atrophy", "hypertrophy", "fibrosis", "sclerosis", "degeneration",
        "cataract", "glaucoma", "neuropathy", "myelopathy",
    ]

    anatomies_flat = []
    for domain_list in ALL_DOMAINS.values():
        anatomies_flat.extend(domain_list)

    lateralities = ["right", "left", "bilateral", "unspecified"]

    entries = []
    seen = set()
    attempts = 0

    while len(entries) < n and attempts < n * 20:
        attempts += 1
        q = random.choice(qualifiers)
        c = random.choice(conditions)
        a = random.choice(anatomies_flat)
        lat = random.choice(lateralities + [""])

        if lat:
            phrase = f"{q} {c} of {lat} {a}"
        else:
            phrase = f"{q} {c} of {a}"

        phrase = phrase.lower()
        if phrase in all_titles or phrase in seen:
            continue
        seen.add(phrase)
        entries.append({
            "text": phrase,
            "label": "FP",
            "category": "template_remix",
            "reason": f"recombined: [{q}] + [{c}] + [{a}]",
        })

    return entries


def gen_novel_english(all_titles: Set[str], n=80) -> List[dict]:
    """Medical words in clearly non-medical contexts. NOT overlapping with fp_dataset.py."""
    medical_adjectives = [
        "chronic", "acute", "malignant", "benign", "congenital",
        "bilateral", "recurrent", "idiopathic", "pathological",
        "degenerative", "inflammatory", "infectious", "progressive",
        "autoimmune", "hereditary", "traumatic", "systemic",
        "superficial", "invasive", "refractory",
    ]

    nonmedical_nouns = [
        "deadline", "meeting", "project", "traffic", "weather",
        "commute", "argument", "procrastination", "bureaucracy",
        "indecision", "perfectionism", "nostalgia", "optimism",
        "pessimism", "ambition", "laziness", "confusion", "delay",
        "budget", "email", "presentation", "homework", "software",
        "management", "leadership", "teamwork", "feedback",
        "strategy", "innovation", "disruption", "workflow",
    ]

    condition_nouns = [
        "fracture", "dislocation", "hemorrhage", "infection",
        "inflammation", "syndrome", "disorder", "disease",
        "sprain", "rupture", "obstruction", "stenosis",
    ]

    nonmedical_contexts = [
        "{adj} shortage of supplies",
        "{adj} backlog in processing",
        "{adj} decline in performance",
        "{adj} failure of the system",
        "{adj} instability in markets",
        "{adj} deterioration of morale",
        "{noun} of the economy",
        "{noun} of public trust",
        "{noun} of the supply chain",
        "{noun} of diplomatic relations",
        "{noun} of communication",
        "{noun} of the foundation",
        "{noun} of confidence",
        "{noun} of logic",
    ]

    entries = []
    seen = set()

    # Pattern 1: medical adj + non-medical noun
    for adj in medical_adjectives:
        for noun in nonmedical_nouns:
            phrase = f"{adj} {noun}"
            if phrase not in all_titles and phrase not in seen:
                seen.add(phrase)
                entries.append({
                    "text": phrase,
                    "label": "FP",
                    "category": "novel_english",
                    "reason": f"medical adj '{adj}' + non-medical noun '{noun}'",
                })

    # Pattern 2: condition noun in non-medical template
    for template in nonmedical_contexts:
        for noun in condition_nouns:
            phrase = template.format(adj=random.choice(medical_adjectives), noun=noun)
            if phrase not in all_titles and phrase not in seen:
                seen.add(phrase)
                entries.append({
                    "text": phrase,
                    "label": "FP",
                    "category": "novel_english",
                    "reason": f"medical term in non-medical context",
                })

    random.shuffle(entries)
    return entries[:n]


def gen_boundary_probes(all_titles: Set[str], n=50) -> List[dict]:
    """Test boundary decisions: single words, partial matches, near-homonyms."""
    entries = []

    # Single medical words (should they match?)
    single_words = [
        ("stenosis", "bare condition noun, no anatomy"),
        ("neoplasm", "bare condition noun, no anatomy"),
        ("embolism", "bare condition noun, no anatomy"),
        ("arthritis", "bare condition noun, no anatomy"),
        ("fibrosis", "bare condition noun, no anatomy"),
        ("edema", "bare condition noun, no anatomy"),
        ("hemorrhage", "bare condition noun, no anatomy"),
        ("thrombosis", "bare condition noun, no anatomy"),
        ("abscess", "bare condition noun, no anatomy"),
        ("gangrene", "bare condition noun, no anatomy"),
    ]

    # Sentence fragments containing real titles
    fragments = [
        ("patient has fracture of femur", "sentence wrapping a real title"),
        ("diagnosed with type 2 diabetes mellitus", "sentence wrapping a real title"),
        ("history of pneumonia", "matches H-code pattern but also conversational"),
        ("presents with acute appendicitis", "sentence wrapping a real title"),
        ("rule out pulmonary embolism", "clinical context, not a title"),
        ("status post cholecystectomy", "procedure, not diagnosis"),
        ("post-surgical wound infection", "compound clinical phrase"),
        ("recurrent urinary tract infection", "natural language, close to real title"),
    ]

    # Plural/possessive variants
    variants = [
        ("fractures of the femur", "'the' article insertion"),
        ("a laceration of the scalp", "article prefix"),
        ("the burn of hand", "article prefix"),
        ("multiple fractures of ribs", "added 'multiple'"),
        ("bilateral sprains of ankles", "plural anatomy"),
        ("old fracture of femur", "'old' qualifier not in ICD"),
        ("healed fracture of tibia", "'healed' qualifier not in ICD"),
        ("possible dislocation of shoulder", "'possible' qualifier"),
        ("suspected embolism of artery", "'suspected' qualifier"),
        ("mild contusion of knee", "'mild' not typical ICD qualifier for contusion"),
    ]

    for text, reason in single_words + fragments + variants:
        if text.lower() not in all_titles:
            entries.append({
                "text": text.lower(),
                "label": "FP",
                "category": "boundary_probe",
                "reason": reason,
            })

    random.shuffle(entries)
    return entries[:n]


def gen_true_positives(all_titles: Set[str], n=300) -> List[dict]:
    """Sample real ICD titles as true positives (different sample from fp_dataset.py)."""
    # Use a different seed offset to get different samples than fp_dataset.py
    titles_list = sorted(all_titles)
    rng = random.Random(7777)
    rng.shuffle(titles_list)

    entries = []
    for t in titles_list[:n]:
        entries.append({
            "text": t,
            "label": "TP",
            "category": "official_title",
        })
    return entries


# ── Main ─────────────────────────────────────────────────────────────

def build():
    print("Loading titles...")
    all_titles = load_all_titles()
    all_terms = load_all_terms()
    print(f"  {len(all_titles)} official titles, {len(all_terms)} total terms")

    print("\nGenerating validation entries...")
    tp_entries = gen_true_positives(all_titles, n=300)
    print(f"  {len(tp_entries)} true positives")

    cross_domain = gen_cross_domain_swaps(all_titles, n=200)
    print(f"  {len(cross_domain)} cross-domain swaps")

    random_combos = gen_random_combos(all_titles, all_terms, n=200)
    print(f"  {len(random_combos)} random combos")

    template = gen_template_remix(all_titles, n=150)
    print(f"  {len(template)} template remixes")

    english = gen_novel_english(all_titles, n=80)
    print(f"  {len(english)} novel English")

    boundary = gen_boundary_probes(all_titles, n=50)
    print(f"  {len(boundary)} boundary probes")

    fp_entries = cross_domain + random_combos + template + english + boundary
    all_entries = tp_entries + fp_entries

    # Verify no FP is actually a real title
    false_fps = [e for e in fp_entries if e["text"].lower() in all_titles]
    if false_fps:
        print(f"\n  WARNING: {len(false_fps)} 'FP' entries are actually real titles! Removing...")
        fp_entries = [e for e in fp_entries if e["text"].lower() not in all_titles]
        all_entries = tp_entries + fp_entries

    # Summary
    from collections import Counter
    label_counts = Counter(e["label"] for e in all_entries)
    cat_counts = Counter(e["category"] for e in all_entries)

    dataset = {
        "metadata": {
            "description": "HELD-OUT validation dataset for ICD-10-CM entity FP testing. "
                           "Systematically generated — not hand-crafted. Tests structural "
                           "correctness, not memorization of known test cases.",
            "version": "1.0",
            "generation_seed": 2026,
            "warning": "This dataset should NOT be used during strategy development. "
                       "It is for final validation only.",
            "categories": {
                "cross_domain_swap": "Real condition swapped to wrong anatomy domain",
                "random_combo": "Random condition × anatomy from ICD vocabulary, not a real title",
                "template_remix": "Recombined qualifier + condition + anatomy from different titles",
                "novel_english": "Medical words in non-medical contexts (different from fp_dataset)",
                "boundary_probe": "Single words, sentence fragments, article/qualifier variants",
                "official_title": "Real ICD-10-CM titles (true positives, different sample)",
            },
            "counts": {
                "by_label": dict(label_counts),
                "by_category": dict(cat_counts),
                "total": len(all_entries),
            },
        },
        "entries": all_entries,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\nValidation dataset written to {OUTPUT_PATH}")
    print(f"Total: {len(all_entries)} entries")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count}")
    print("By category:")
    for cat, count in sorted(cat_counts.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    build()
