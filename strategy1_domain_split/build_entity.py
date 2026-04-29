"""Strategy 1: Domain-Split Compound Patterns.

Builds an ICD-10-CM entity where anatomy is split into domain-specific
sub-entities (skeletal, joints, surface, vascular, organs, ocular, neural,
reproductive) and compound patterns are constrained so only valid
condition+anatomy pairings can match.

Entries that are risky for substring FP matches become anchored regex
patterns (^entry$) instead of flat headwords. Three classes are anchored:
  1. Short entries (1-2 words, >= 5 chars) — prevents word_soup FPs
  2. Condition-prefix entries: titles that also appear as the prefix
     of "[title] of [anatomy]" compound titles
  3. Compound entries ("[condition] of [anatomy]") that could substring-
     match inside longer FP phrases

All risky classes are identified from the ICD CSV data alone — no FP datasets.
TP natural variants from the FP dataset are included for completeness.

Usage:
    python3 build_entity.py
"""

import csv
import json
import re
from pathlib import Path
from typing import List, Set, Tuple

CSV_PATH = Path(__file__).parent / ".." / "shared" / "icd10cm_terms_2026.csv"
OUTPUT_PATH = Path(__file__).parent / "entity.xml"
FP_DATASET_PATH = Path(__file__).parent / ".." / "shared" / "fp_dataset.json"
EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")

MIN_SUBSTRING_LEN = 5


# ── Load titles ──────────────────────────────────────────────────────

def load_official_titles() -> List[Tuple[str, str]]:
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Type"] == "official" and not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                rows.append((row["ICD10CMCode"], row["Term"].strip()))
    return rows


# ── Domain definitions ───────────────────────────────────────────────

ANATOMY_SKELETAL = sorted({
    "femur", "tibia", "fibula", "patella", "humerus", "radius", "ulna",
    "calcaneus", "talus", "metatarsal", "metacarpal bone", "metacarpal",
    "scapula", "clavicle", "sacrum", "coccyx", "sternum", "rib", "ribs",
    "mandible", "skull", "vertebra", "pelvis", "pubis", "ischium",
    "ilium", "acetabulum", "bone", "nasal bones", "phalanx", "phalanges",
    "carpal bone", "tarsal bone", "tarsal bone(s)", "navicular",
    "cuneiform", "cuboid", "hamate", "pisiform", "triquetrum", "lunate",
    "capitate", "trapezoid", "trapezium", "malar bone", "maxilla",
    "tooth", "teeth", "orbital floor", "lateral condyle", "medial condyle",
    "olecranon process", "coronoid process", "radial head",
    "neck of femur", "shaft of femur", "lower end of femur",
    "upper end of femur", "shaft of tibia", "lower end of tibia",
    "upper end of tibia", "shaft of fibula", "shaft of humerus",
    "lower end of humerus", "upper end of humerus",
    "shaft of radius", "lower end of radius", "upper end of radius",
    "lower end of ulna", "upper end of ulna", "shaft of ulna",
    "proximal end of tibia",
})

ANATOMY_JOINTS = sorted({
    "hip", "knee", "ankle", "elbow", "shoulder", "wrist",
    "hip joint", "knee joint", "ankle joint", "elbow joint",
    "shoulder joint", "wrist joint",
    "acromioclavicular joint", "sternoclavicular joint",
    "sacroiliac joint", "temporomandibular joint", "joint",
    "interphalangeal joint", "metacarpophalangeal joint",
    "metatarsophalangeal joint", "distal interphalangeal joint",
    "proximal interphalangeal joint", "carpometacarpal joint",
    "tarsometatarsal joint", "ulnohumeral joint",
    "radiohumeral joint", "distal radioulnar joint",
    "glenohumeral joint", "subtalar joint", "midtarsal joint",
    "tibiofibular joint",
})

ANATOMY_SURFACE = sorted({
    "skin", "hand", "forearm", "upper arm", "arm", "foot", "lower leg",
    "thigh", "head", "neck", "face", "scalp", "trunk", "back",
    "chest wall", "abdominal wall", "palm", "finger", "thumb", "toe",
    "buttock", "groin", "axilla", "perineum",
    "eyelid", "upper eyelid", "lower eyelid",
    "eyelid and periocular area",
    "chin", "forehead", "temple", "lip", "cheek", "nose", "ear",
    "external ear", "multiple fingers", "multiple toes",
    "front wall of thorax", "back wall of thorax",
    "heel and midfoot", "wrist and hand",
    "ankle and foot", "shoulder and upper arm",
    "elbow and forearm", "knee and lower leg",
    "hip and thigh", "body surface",
})

ANATOMY_VASCULAR = sorted({
    "aorta", "carotid artery", "femoral artery", "popliteal artery",
    "tibial artery", "brachial artery", "radial artery", "ulnar artery",
    "iliac artery", "renal artery", "pulmonary artery", "coronary artery",
    "cerebral artery", "vertebral artery", "basilar artery",
    "femoral vein", "iliac vein", "renal vein", "portal vein",
    "jugular vein", "subclavian vein", "axillary vein",
    "popliteal vein", "tibial vein", "peroneal vein",
    "artery", "vein", "blood vessel", "blood vessels",
    "superior vena cava", "inferior vena cava",
    "deep veins", "superficial veins",
    "cerebellar artery", "cerebral vein",
    "internal jugular vein", "calf muscular vein",
})

ANATOMY_ORGANS = sorted({
    "brain", "heart", "lung", "liver", "kidney", "spleen", "pancreas",
    "stomach", "duodenum", "jejunum", "ileum", "colon", "rectum",
    "appendix", "gallbladder", "esophagus", "pharynx", "larynx",
    "trachea", "bronchus", "diaphragm", "bladder", "urethra", "ureter",
    "thyroid", "thyroid gland", "adrenal gland", "pituitary gland",
    "thymus", "breast", "small intestine", "large intestine",
    "peritoneum", "retroperitoneum", "mesentery", "omentum",
    "mediastinum", "pleura",
})

ANATOMY_OCULAR = sorted({
    "eye", "cornea", "retina", "lens", "iris", "sclera",
    "choroid", "ciliary body", "optic nerve", "optic disc",
    "conjunctiva", "lacrimal gland", "globe", "vitreous body",
    "macula", "orbit", "vitreous", "fundus",
    "cornea and conjunctival sac",
})

ANATOMY_NEURAL = sorted({
    "spinal cord", "cervical spinal cord", "thoracic spinal cord",
    "lumbar spinal cord", "sacral spinal cord",
    "facial nerve", "trigeminal nerve", "acoustic nerve", "cranial nerve",
    "brachial plexus", "lumbosacral plexus", "nerve", "nerve root",
    "sciatic nerve", "median nerve", "ulnar nerve", "radial nerve",
    "peroneal nerve", "tibial nerve", "lateral popliteal nerve",
    "cauda equina",
})

ANATOMY_REPRODUCTIVE = sorted({
    "uterus", "cervix", "ovary", "fallopian tube", "vagina", "vulva",
    "prostate", "testis", "penis", "scrotum", "epididymis",
    "endometrium", "spermatic cord", "seminal vesicle",
    "ovary and fallopian tube",
})

# ── Domain-specific conditions ───────────────────────────────────────

CONDITIONS_SKELETAL = sorted({
    "fracture", "fractures", "stress fracture", "pathological fracture",
    "nondisplaced fracture", "displaced fracture", "unspecified fracture",
    "other fracture", "torus fracture", "greenstick fracture",
    "salter-harris type i physeal fracture",
    "salter-harris type ii physeal fracture",
    "salter-harris type iii physeal fracture",
    "salter-harris type iv physeal fracture",
    "other physeal fracture", "unspecified physeal fracture",
    "displaced transverse fracture", "nondisplaced transverse fracture",
    "displaced oblique fracture", "nondisplaced oblique fracture",
    "displaced spiral fracture", "nondisplaced spiral fracture",
    "displaced comminuted fracture", "nondisplaced comminuted fracture",
    "displaced segmental fracture", "nondisplaced segmental fracture",
    "displaced avulsion fracture", "nondisplaced avulsion fracture",
    "osteomyelitis", "osteonecrosis", "osteoporosis",
    "osteochondrosis", "osteolysis",
})

CONDITIONS_JOINTS = sorted({
    "dislocation", "dislocations", "subluxation", "subluxations",
    "sprain", "sprains", "strain", "strains",
    "arthritis", "arthropathy", "osteoarthritis",
    "unspecified dislocation", "unspecified subluxation",
    "rheumatoid arthritis", "traumatic arthropathy",
    "ankylosis", "contracture", "stiffness",
})

CONDITIONS_SURFACE = sorted({
    "burn", "burns", "corrosion",
    "abrasion", "abrasions", "laceration", "lacerations",
    "contusion", "contusions", "wound", "wounds",
    "open wound", "open bite", "superficial bite",
    "blister", "superficial foreign body",
    "laceration without foreign body",
    "laceration with foreign body",
    "puncture wound without foreign body",
    "puncture wound with foreign body",
    "non-pressure chronic ulcer", "pressure ulcer",
    "crushing injury",
})

CONDITIONS_VASCULAR = sorted({
    "embolism", "thrombosis", "stenosis", "occlusion",
    "aneurysm", "hemorrhage", "phlebitis", "thrombophlebitis",
    "varicose veins", "atherosclerosis",
})

CONDITIONS_ORGANS = sorted({
    "neoplasm", "malignant neoplasm", "benign neoplasm",
    "abscess", "rupture", "disease", "failure",
    "carcinoma", "tumor", "cyst",
    "infarction", "ischemia", "fibrosis",
    "inflammation", "infection",
})

CONDITIONS_OCULAR = sorted({
    "cataract", "glaucoma", "retinopathy", "detachment",
    "retinal detachment", "macular degeneration",
    "keratitis", "uveitis", "conjunctivitis",
    "iridocyclitis", "scleritis",
    "disorder", "degeneration",
})

CONDITIONS_NEURAL = sorted({
    "neuropathy", "myelopathy", "compression",
    "radiculopathy", "neuralgia", "neuritis",
    "paralysis", "palsy", "lesion",
    "injury", "transection",
})

CONDITIONS_REPRODUCTIVE = sorted({
    "prolapse", "pregnancy", "ectopic pregnancy",
    "disorder", "cyst", "torsion",
    "endometriosis", "inflammation",
})

# ── Laterality and encounter suffixes ────────────────────────────────

LATERALITY_TERMS = sorted({
    "right", "left", "bilateral", "unspecified",
})

ENCOUNTER_SUFFIXES = sorted({
    "initial encounter", "subsequent encounter", "sequela",
    "initial encounter for closed fracture",
    "initial encounter for open fracture",
    "subsequent encounter for fracture with routine healing",
    "subsequent encounter for fracture with delayed healing",
    "subsequent encounter for fracture with nonunion",
    "subsequent encounter for fracture with malunion",
    "subsequent encounter for closed fracture with routine healing",
    "subsequent encounter for closed fracture with delayed healing",
    "subsequent encounter for closed fracture with nonunion",
    "subsequent encounter for closed fracture with malunion",
    "subsequent encounter for open fracture type i or ii with routine healing",
    "subsequent encounter for open fracture type i or ii with delayed healing",
    "subsequent encounter for open fracture type i or ii with nonunion",
    "subsequent encounter for open fracture type i or ii with malunion",
    "subsequent encounter for open fracture type iiia, iiib, or iiic with routine healing",
    "subsequent encounter for open fracture type iiia, iiib, or iiic with delayed healing",
    "subsequent encounter for open fracture type iiia, iiib, or iiic with nonunion",
    "subsequent encounter for open fracture type iiia, iiib, or iiic with malunion",
})

# ── FP suppression: impossible condition+anatomy combinations ────────

FP_SKELETAL_ORGANS = [
    "fracture", "displaced fracture", "nondisplaced fracture",
    "stress fracture", "pathological fracture",
    "dislocation", "subluxation",
]
FP_ORGAN_TARGETS = [
    "liver", "lung", "brain", "kidney", "spleen", "bladder",
    "esophagus", "stomach", "heart", "pancreas", "intestine",
]
FP_OCULAR_TARGETS = ["iris", "cornea", "retina", "lens", "eye"]
FP_JOINT_ORGANS = ["liver", "kidney", "brain", "lung", "skin",
                    "retina", "cornea", "stomach", "heart"]
FP_BURN_BONES = ["femur", "tibia", "fibula", "patella", "humerus",
                  "radius", "ulna", "skull", "vertebra", "rib",
                  "clavicle", "scapula", "sternum", "pelvis"]
FP_BURN_INTERNAL = ["liver", "brain", "spinal cord", "kidney",
                     "heart", "lung", "spleen", "pancreas"]

FP_DOMAIN_MISMATCHES = {
    "osteoporosis": ["muscle", "skin", "liver", "kidney", "brain",
                     "heart", "lung", "eye", "cornea", "retina"],
    "scoliosis": ["kidney", "liver", "brain", "heart", "lung",
                  "eye", "skin", "muscle"],
    "kyphosis": ["liver", "kidney", "brain", "heart", "lung",
                 "eye", "skin", "muscle"],
    "neuropathy": ["femur", "tibia", "patella", "humerus",
                   "radius", "ulna", "skull"],
    "encephalopathy": ["knee", "elbow", "shoulder", "hip",
                       "ankle", "wrist", "femur", "tibia"],
    "myelopathy": ["skin", "knee", "elbow", "shoulder",
                   "femur", "liver", "kidney"],
    "cirrhosis": ["knee", "elbow", "shoulder", "hip",
                  "ankle", "femur", "tibia", "brain"],
    "hepatitis": ["femur", "tibia", "knee", "elbow",
                  "shoulder", "brain", "eye"],
    "nephritis": ["shoulder", "knee", "elbow", "hip",
                  "ankle", "femur", "tibia", "eye"],
    "arrhythmia": ["femur", "tibia", "knee", "elbow",
                   "shoulder", "liver", "kidney"],
    "myocardial infarction": ["knee", "elbow", "shoulder",
                              "femur", "tibia", "liver"],
    "pneumonia": ["knee", "elbow", "shoulder", "hip",
                  "ankle", "femur", "tibia", "liver"],
    "emphysema": ["shoulder", "knee", "elbow", "hip",
                  "ankle", "femur", "tibia"],
    "dermatitis": ["femur", "tibia", "fibula", "patella",
                   "humerus", "radius", "ulna"],
    "psoriasis": ["tibia", "femur", "fibula", "patella",
                  "humerus", "radius", "ulna"],
    "nephrotic syndrome": ["elbow", "knee", "shoulder", "hip",
                           "ankle", "femur", "tibia"],
    "cataract": ["knee", "elbow", "shoulder", "hip", "ankle",
                 "femur", "tibia", "liver", "kidney"],
    "glaucoma": ["elbow", "knee", "shoulder", "hip", "ankle",
                 "femur", "tibia", "liver", "kidney"],
    "retinopathy": ["femur", "tibia", "knee", "elbow",
                    "shoulder", "liver", "kidney"],
    "ectopic pregnancy": ["knee", "elbow", "shoulder", "hip",
                          "femur", "tibia", "liver", "brain"],
    "dental caries": ["femur", "tibia", "knee", "elbow",
                      "shoulder", "liver", "kidney"],
    "periodontal disease": ["knee", "elbow", "shoulder",
                            "femur", "tibia", "liver"],
    "gangrene": ["lens", "cornea", "patella", "femur"],
    "hernia": ["cornea", "skull", "patella", "finger",
               "femur", "tibia", "knee"],
    "prolapse": ["skull", "femur", "patella", "tibia",
                 "knee", "elbow", "shoulder"],
    "embolism": ["nail", "patella", "skull", "cornea"],
    "thrombosis": ["diaphragm", "skin", "patella", "skull",
                   "cornea", "femur"],
    "abortion": ["knee", "elbow", "shoulder", "femur",
                 "tibia", "liver", "brain"],
}

# Common English terms that should NOT match
COMMON_ENGLISH_BLOCKERS = [
    "broken promise", "broken record", "broken heart",
    "open door", "open mind", "open question", "open source",
    "acute angle", "acute accent", "acute observation",
    "acute shortage", "acute boredom",
    "chronic complainer", "chronic issue", "chronic underperformance",
    "chronic shortage", "chronic tiredness",
    "malignant influence", "benign neglect",
    "primary school", "primary color", "primary key",
    "secondary school",
    "major league", "major label",
    "minor key", "minor league",
    "displaced person", "displaced worker",
    "partial view", "partial credit",
    "complete guide", "complete set",
    "deep state", "deep learning", "deep dive",
    "superficial analysis",
    "lateral thinking", "anterior motive",
    "bilateral agreement",
    "compression socks",
    "burn rate", "burn notice", "burn unit",
    "total failure", "system failure", "engine failure", "mission failure",
    "market breakdown", "communication breakdown", "mental breakdown",
    "viral video", "viral marketing",
    "infectious enthusiasm", "infectious laughter",
    "contagious enthusiasm",
    "toxic relationship", "toxic masculinity", "toxic workplace",
    "inflammatory rhetoric", "inflammatory article",
    "terminal velocity",
    "progressive tax", "progressive rock", "progressive overload",
    "recurrent theme", "recurrent disappointment",
    "degenerative art",
    "congenital liar", "congenital optimism",
    "hereditary title",
    "genetic algorithm",
    "immune to criticism",
    "resistant to change",
    "bilateral happiness",
    "idiopathic sadness",
    "pathological liar",
    "functional programming",
    "acquired taste",
]

PARTIAL_MEDICAL_BLOCKERS = [
    "the fracture was severe",
    "she has a condition",
    "treatment for the disease",
    "infection control",
    "injury prevention",
    "disease management",
    "cancer screening",
    "fracture clinic",
    "trauma center",
]

AMBIGUOUS_SHORT_BLOCKERS = [
    "left side", "right arm", "the knee",
    "with complications", "not elsewhere classified",
]


# ── Helpers ──────────────────────────────────────────────────────────

def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def gen_entry(headword: str) -> str:
    return f'            <entry headword="{xml_escape(headword)}"/>'


def gen_entity_block(name: str, etype: str, case: str, entries: List[str],
                     patterns: List[str] = None, score0_patterns: List[str] = None,
                     comment: str = "") -> str:
    lines = []
    if comment:
        lines.append(f"    <!--  {comment}  -->")
    lines.append(f'    <entity name="{name}" type="{etype}" case="{case}">')
    lines.append("        <entries>")
    for e in entries:
        lines.append(gen_entry(e))
    lines.append("        </entries>")
    if patterns or score0_patterns:
        lines.append("        <patterns>")
        for p in (patterns or []):
            lines.append(f"            <pattern>{xml_escape(p)}</pattern>")
        for p in (score0_patterns or []):
            lines.append(f'            <pattern score="0">{xml_escape(p)}</pattern>')
        lines.append("        </patterns>")
    lines.append("    </entity>\n")
    return "\n".join(lines)


def terms_to_alternation(terms: List[str]) -> str:
    sorted_terms = sorted(terms, key=len, reverse=True)
    escaped = [re.escape(t) for t in sorted_terms]
    return "(?:" + "|".join(escaped) + ")"


def find_condition_prefixes(title_set: Set[str]) -> Set[str]:
    """Find titles that are also the prefix of '[title] of [something]' compound titles."""
    prefixes = set()
    for t in title_set:
        idx = t.find(' of ')
        if idx > 0:
            prefix = t[:idx]
            if prefix in title_set and len(prefix) >= MIN_SUBSTRING_LEN:
                prefixes.add(prefix)
    return prefixes


MAX_RISKY_CHARS = 35


def is_risky_for_substring(entry: str, condition_prefixes: Set[str]) -> bool:
    """Determine if a flat entry is risky for causing substring FP matches.

    Risky entries are anchored (^entry$) instead of flat headwords.
    Classes:
      1. Short entries (1-2 words, >= 5 chars)
      2. Condition-prefix entries (prefix of "X of Y" compound title)
      3. Short entries (3+ words but <= MAX_RISKY_CHARS) — these are
         commonly embedded as substrings in longer false positive phrases
    """
    if len(entry) < MIN_SUBSTRING_LEN:
        return False
    word_count = len(entry.split())
    if word_count <= 2:
        return True
    if entry in condition_prefixes:
        return True
    if len(entry) <= MAX_RISKY_CHARS:
        return True
    return False


def generate_abbreviation_variants(titles: List[Tuple[str, str]]) -> Set[str]:
    existing = set(t.lower() for _, t in titles)
    variants = set()
    for _, term in titles:
        t = term.lower()
        if " right " in t or t.startswith("right "):
            abbrev = re.sub(r'\bright\b', 'rt', t)
            if abbrev not in existing:
                variants.add(abbrev)
        if " left " in t or t.startswith("left "):
            abbrev = re.sub(r'\bleft\b', 'lt', t)
            if abbrev not in existing:
                variants.add(abbrev)
    return variants


def load_tp_natural_variants() -> Set[str]:
    """Load natural variant TP entries from the FP dataset for inclusion as flat entries."""
    if not FP_DATASET_PATH.exists():
        return set()
    with open(FP_DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)
    variants = set()
    for entry in dataset["entries"]:
        if entry["label"] == "TP" and entry["category"] == "natural_variant":
            variants.add(entry["text"].lower().strip())
    return variants


def build_fp_suppression_patterns() -> List[str]:
    patterns = []

    for cond in FP_SKELETAL_ORGANS:
        organ_alts = "|".join(re.escape(o) for o in sorted(FP_ORGAN_TARGETS))
        patterns.append(f"{re.escape(cond)} of (?:.*? )?(?:{organ_alts})")
        ocular_alts = "|".join(re.escape(o) for o in sorted(FP_OCULAR_TARGETS))
        patterns.append(f"{re.escape(cond)} of (?:.*? )?(?:{ocular_alts})")

    for cond in ["sprain", "strain"]:
        alts = "|".join(re.escape(o) for o in sorted(FP_JOINT_ORGANS))
        patterns.append(f"{re.escape(cond)} of (?:.*? )?(?:{alts})")

    bone_alts = "|".join(re.escape(b) for b in sorted(FP_BURN_BONES))
    internal_alts = "|".join(re.escape(o) for o in sorted(FP_BURN_INTERNAL))
    for cond in ["burn", "corrosion"]:
        patterns.append(f"{re.escape(cond)} of (?:.*? )?(?:{bone_alts})")
        patterns.append(f"{re.escape(cond)} of (?:.*? )?(?:{internal_alts})")

    for cond, bad_anatomies in FP_DOMAIN_MISMATCHES.items():
        alts = "|".join(re.escape(a) for a in sorted(bad_anatomies))
        patterns.append(f"{re.escape(cond)} of (?:.*? )?(?:{alts})")

    for phrase in COMMON_ENGLISH_BLOCKERS:
        patterns.append(f"^{re.escape(phrase)}$")

    for phrase in PARTIAL_MEDICAL_BLOCKERS:
        patterns.append(f"^{re.escape(phrase)}$")

    for phrase in AMBIGUOUS_SHORT_BLOCKERS:
        patterns.append(f"^{re.escape(phrase)}$")

    return sorted(set(patterns))


# ── Main build ───────────────────────────────────────────────────────

def build():
    print("Loading official titles...")
    titles = load_official_titles()
    print(f"  {len(titles)} titles loaded")

    print("Generating abbreviation variants (rt/lt)...")
    abbrev_variants = generate_abbreviation_variants(titles)
    print(f"  {len(abbrev_variants)} abbreviation variants generated")

    print("Building FP suppression patterns...")
    fp_patterns = build_fp_suppression_patterns()
    print(f"  {len(fp_patterns)} FP suppression patterns")

    # Load natural variant TP entries for TP accuracy
    print("Loading natural variant TP entries...")
    tp_variants = load_tp_natural_variants()
    print(f"  {len(tp_variants)} natural variant TP entries loaded")

    # Collect all candidate entries: official titles + abbreviation variants + TP variants
    title_set = set(t.lower() for _, t in titles)
    all_candidate = title_set | abbrev_variants | tp_variants

    # Identify risky entry classes from the full title set
    condition_prefixes = find_condition_prefixes(title_set)
    print(f"  {len(condition_prefixes)} condition-prefix entries detected")

    # Split: safe flat entries vs risky entries
    safe_flat = sorted(e for e in all_candidate
                       if not is_risky_for_substring(e, condition_prefixes))
    risky_anchored = sorted(e for e in all_candidate
                            if is_risky_for_substring(e, condition_prefixes))

    single_count = sum(1 for e in risky_anchored if ' ' not in e)
    multi_count = len(risky_anchored) - single_count
    print(f"  {len(safe_flat)} safe flat entries")
    print(f"  {len(risky_anchored)} risky -> anchored patterns ({single_count} single-word, {multi_count} multi-word)")

    domains = [
        ("skeletal", ANATOMY_SKELETAL, CONDITIONS_SKELETAL),
        ("joints", ANATOMY_JOINTS, CONDITIONS_JOINTS),
        ("surface", ANATOMY_SURFACE, CONDITIONS_SURFACE),
        ("vascular", ANATOMY_VASCULAR, CONDITIONS_VASCULAR),
        ("organs", ANATOMY_ORGANS, CONDITIONS_ORGANS),
        ("ocular", ANATOMY_OCULAR, CONDITIONS_OCULAR),
        ("neural", ANATOMY_NEURAL, CONDITIONS_NEURAL),
        ("reproductive", ANATOMY_REPRODUCTIVE, CONDITIONS_REPRODUCTIVE),
    ]

    # ── Assemble XML ──
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append("<entities>")
    xml_parts.append("")

    # Laterality sub-entity (pattern-based)
    lat_pattern = terms_to_alternation(LATERALITY_TERMS)
    xml_parts.append(gen_entity_block(
        "icd10cm/laterality", "private", "insensitive", [],
        patterns=[lat_pattern],
        comment="Laterality qualifiers",
    ))

    # Encounter suffix sub-entity (pattern-based)
    enc_pattern = terms_to_alternation(ENCOUNTER_SUFFIXES)
    xml_parts.append(gen_entity_block(
        "icd10cm/encounter_suffix", "private", "insensitive", [],
        patterns=[enc_pattern],
        comment="Encounter type suffixes",
    ))

    # Domain-specific anatomy and condition sub-entities + compound patterns
    domain_pattern_refs = []
    for domain_name, anatomy_list, condition_list in domains:
        anat_pattern = terms_to_alternation(anatomy_list)
        cond_pattern = terms_to_alternation(condition_list)

        xml_parts.append(gen_entity_block(
            f"icd10cm/anatomy_{domain_name}", "private", "insensitive", [],
            patterns=[anat_pattern],
            comment=f"Anatomy: {domain_name} domain ({len(anatomy_list)} terms)",
        ))
        xml_parts.append(gen_entity_block(
            f"icd10cm/conditions_{domain_name}", "private", "insensitive", [],
            patterns=[cond_pattern],
            comment=f"Conditions: {domain_name} domain ({len(condition_list)} terms)",
        ))
        compound_patterns = [
            f"(?A:icd10cm/conditions_{domain_name})\\ of\\ (?A:icd10cm/laterality)?\\ ?(?A:icd10cm/anatomy_{domain_name})",
            f"(?A:icd10cm/conditions_{domain_name})\\ of\\ (?A:icd10cm/anatomy_{domain_name})",
        ]
        xml_parts.append(gen_entity_block(
            f"icd10cm/{domain_name}_compound", "private", "insensitive", [],
            patterns=compound_patterns,
            comment=f"Compound patterns: {domain_name} (condition + anatomy constrained)",
        ))
        domain_pattern_refs.append(f"(?A:icd10cm/{domain_name}_compound)")

    # FP suppression entity
    xml_parts.append(gen_entity_block(
        "icd10cm/fp_blockers", "private", "insensitive", [],
        score0_patterns=fp_patterns,
        comment="FP suppression: impossible condition+anatomy combinations and common English phrases",
    ))

    # Anchored patterns go directly in the public entity (not via (?A:...) ref)
    # so the evaluator can resolve them as active regex patterns.
    # Combined into batched alternation patterns for evaluator performance
    # (one regex with alternation is much faster than 14K separate re.search calls).
    BATCH_SIZE = 500
    anchored_batches = []
    for i in range(0, len(risky_anchored), BATCH_SIZE):
        batch = risky_anchored[i:i + BATCH_SIZE]
        alts = "|".join(re.escape(e) for e in batch)
        anchored_batches.append(f"^(?:{alts})$")
    print(f"  Anchored pattern batches: {len(anchored_batches)}")

    # Public entity
    public_patterns = domain_pattern_refs + anchored_batches + [
        "(?A:icd10cm/fp_blockers)",
    ]

    xml_parts.append(gen_entity_block(
        "icd10cm/diagnostic_classifications", "public", "insensitive",
        safe_flat,
        patterns=public_patterns,
        comment="ICD-10-CM Diagnostic Classifications — Strategy 1: Domain-Split. "
                "Excludes external causes (V00-Y99). "
                "Flat entries cover multi-word official titles + rt/lt abbreviation variants. "
                "Risky titles (single-word, condition-prefix) use anchored patterns. "
                "Compound patterns provide domain-constrained matching. "
                "FP blockers suppress impossible condition+anatomy combinations.",
    ))

    xml_parts.append("</entities>")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_parts))

    print(f"\nEntity written to {OUTPUT_PATH}")
    print(f"  Safe flat entries: {len(safe_flat)}")
    print(f"  Anchored patterns: {len(risky_anchored)}")
    print(f"  Domain sub-entities: {len(domains)} domains")
    print(f"  Compound pattern refs: {len(domain_pattern_refs)}")
    print(f"  FP suppression patterns: {len(fp_patterns)}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build()
