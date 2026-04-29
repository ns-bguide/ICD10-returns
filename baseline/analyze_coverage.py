"""Analyze how well the ICD-10-CM entity covers official titles.

This script simulates matching by checking whether each official title
would be caught by the entity's flat entries, morphological patterns,
or compound condition+anatomy patterns.

It reports:
  - Overall coverage %
  - Coverage by ICD chapter
  - Coverage by match type (flat, morphological, compound, specific)
  - Uncovered titles (gaps) with frequency analysis
"""

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


CSV_PATH = Path(__file__).parent / ".." / "shared" / "icd10cm_terms_2026.csv"
EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")


def load_official_titles() -> List[Tuple[str, str]]:
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Type"] == "official" and not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                rows.append((row["ICD10CMCode"], row["Term"].strip().lower()))
    return rows


def strip_encounter_suffix(title: str) -> str:
    title = re.sub(r",\s*(initial|subsequent)\s+encounter.*$", "", title)
    title = re.sub(r",\s*sequela(\s.*)?$", "", title)
    return title.strip()


# ── Build matching components ──────────────────────────────────────

MORPHOLOGICAL_SUFFIXES = [
    "itis", "osis", "emia", "pathy", "uria", "algia", "ectomy",
    "plasty", "scopy", "ostomy", "otomy", "rrhagia", "rrhea",
    "opia", "asis", "iasis", "oma", "ism",
    "phobia", "philia", "megaly", "cephaly", "phagia", "stasis",
    "plegia", "paresis", "spasm", "plasia",
    "cele", "lysis", "malacia", "ectasis",
    "dynia", "gnosia", "somnia",
    "praxia", "phasia", "phonia", "pnea", "mnesia",
    "cusis", "tonia", "kinesia",
]

MORPHOLOGICAL_FP = {
    "television", "supervision", "provision", "revision",
    "admission", "permission", "commission", "transmission",
    "profession", "expression", "impression",
    "possession", "obsession", "concession", "succession",
    "aggression", "regression", "progression",
    "suppression", "oppression", "fashion", "nation",
    "station", "location", "relation", "emotion", "promotion",
    "tradition", "condition", "position", "operation",
    "situation", "education", "motion",
}


def has_morphological_match(title: str) -> bool:
    """Check if any word in the title has a medical morphological suffix."""
    for word in title.split():
        word = re.sub(r"[^a-z-]", "", word)
        if not word or len(word) < 6:
            continue
        if word in MORPHOLOGICAL_FP:
            continue
        for suf in MORPHOLOGICAL_SUFFIXES:
            if word.endswith(suf) and len(word) > len(suf) + 2:
                return True
    return False


# Condition nouns (high confidence)
CONDITION_NOUNS_HIGH = {
    "fracture", "fractures", "dislocation", "dislocations",
    "subluxation", "subluxations", "laceration", "lacerations",
    "contusion", "contusions", "abrasion", "abrasions",
    "sprain", "sprains", "strain", "strains",
    "injury", "injuries", "wound", "wounds",
    "hemorrhage", "hemorrhages", "rupture", "ruptures",
    "stenosis", "obstruction", "occlusion", "embolism",
    "thrombosis", "infarction", "neoplasm", "neoplasms",
    "carcinoma", "lymphoma", "melanoma", "leukemia", "sarcoma",
    "mesothelioma", "abscess", "abscesses", "ulcer", "ulcers",
    "hernia", "prolapse", "fistula", "cyst", "cysts",
    "polyp", "polyps", "gangrene", "necrosis", "fibrosis",
    "sclerosis", "edema", "effusion", "atrophy", "hypertrophy",
    "hyperplasia", "hypoplasia", "atresia", "ectasia",
    "degeneration", "calcification", "erosion",
    "adhesion", "adhesions", "perforation", "amputation",
    "sepsis", "infection", "infections", "inflammation",
    "syndrome", "disorder", "disorders", "disease", "diseases",
    "deficiency", "deficiencies", "complication", "complications",
    "malformation", "malformations", "deformity", "deformities",
    "insufficiency", "dysfunction", "anomaly", "anomalies",
    "lesion", "lesions", "tumor", "tumors", "cancer", "cancers",
}

CONDITION_NOUNS_LOW = {
    "burn", "burns", "corrosion", "poisoning", "bite", "bites",
    "sting", "stings", "failure", "compression", "restriction",
    "swelling", "tenderness", "weakness", "numbness",
    "detachment", "displacement", "breakdown", "fragmentation",
    "opacity", "ptosis",
}

ANATOMY_TERMS = {
    "femur", "patella", "humerus", "radius", "ulna", "tibia", "fibula",
    "calcaneus", "talus", "metatarsal", "metacarpal bone", "scapula",
    "clavicle", "sacrum", "coccyx", "sternum", "mandible", "skull",
    "pelvis", "pubis", "ischium", "ilium", "acetabulum",
    "hip joint", "knee joint", "ankle joint", "elbow joint", "shoulder joint",
    "wrist", "ankle", "knee", "elbow", "shoulder", "hip",
    "acromioclavicular joint", "sternoclavicular joint", "sacroiliac joint",
    "temporomandibular joint", "ulnohumeral joint",
    "arm", "forearm", "upper arm", "hand", "finger", "thumb",
    "index finger", "middle finger", "ring finger", "little finger",
    "leg", "lower leg", "thigh", "foot", "toe", "great toe",
    "head", "neck", "face", "scalp", "trunk", "back", "lower back",
    "buttock", "groin", "flank", "axilla", "perineum",
    "abdominal wall", "chest wall",
    "brain", "cerebrum", "cerebellum", "brainstem", "spinal cord",
    "cervical spinal cord", "thoracic spinal cord", "lumbar spinal cord",
    "heart", "lung", "liver", "kidney", "spleen", "pancreas",
    "stomach", "duodenum", "jejunum", "ileum", "colon", "rectum",
    "appendix", "gallbladder", "esophagus", "pharynx", "larynx",
    "trachea", "bronchus", "diaphragm", "bladder", "urethra", "ureter",
    "uterus", "cervix", "ovary", "fallopian tube", "vagina", "vulva",
    "prostate", "testis", "penis", "scrotum", "epididymis",
    "thyroid", "adrenal gland", "pituitary gland", "thymus",
    "eye", "eyelid", "cornea", "retina", "lens", "iris", "sclera",
    "choroid", "ciliary body", "optic nerve", "conjunctiva", "globe",
    "vitreous body", "macula", "orbit",
    "ear", "inner ear", "middle ear", "external ear", "ear drum",
    "tympanic membrane", "mastoid",
    "aorta", "carotid artery", "femoral artery", "coronary artery",
    "cerebral artery", "vertebral artery", "pulmonary artery",
    "femoral vein", "jugular vein", "pulmonary vessels",
    "muscle", "tendon", "ligament", "bursa", "cartilage",
    "achilles tendon", "rotator cuff",
    "skin", "nail", "bone", "bone marrow", "joint",
    "meninges", "peritoneum", "pleura", "pericardium",
    "breast", "nipple", "mouth", "tongue", "lip", "palate",
    "tonsil", "nose", "sinus", "bile duct",
    "eyelid and periocular area",
    "upper extremity", "lower extremity",
    "anus", "large intestine", "small intestine",
    "external genital organs",
    "abdominal aorta", "thoracic aorta",
    "front wall of thorax", "back wall of thorax",
}

CONDITION_ADJECTIVES = {
    "abraded", "amputated", "broken", "bruised", "burned", "collapsed",
    "compressed", "contused", "corroded", "crushed", "deformed",
    "detached", "diseased", "dislocated", "dismembered",
    "fractured", "gangrenous", "impacted", "infected", "inflamed",
    "injured", "lacerated", "malformed", "necrotic", "obstructed",
    "occluded", "perforated", "prolapsed", "punctured", "ruptured",
    "severed", "shattered", "sprained", "stenotic", "strangulated",
    "swollen", "torn", "ulcerated",
}

MEDICAL_ADJECTIVES = {
    "abnormal", "acquired", "active", "acute", "advanced",
    "age-related", "allergic", "asymmetrical", "asymptomatic", "atypical",
    "autoimmune", "bacterial", "benign", "bilateral", "chronic",
    "clinical", "communicable", "complex", "complicated",
    "congenital", "contagious", "degenerative", "diabetic",
    "diffuse", "early", "familial", "febrile", "fetal", "focal",
    "fulminant", "functional", "generalized", "genetic", "gestational",
    "hereditary", "hypertensive", "iatrogenic", "idiopathic",
    "immune", "infantile", "infectious", "inflammatory", "inherited",
    "intermittent", "intractable", "invasive", "ischemic",
    "juvenile", "late", "localized", "malignant", "maternal",
    "metastatic", "mucosal", "neonatal", "neurogenic", "nodular",
    "nontoxic", "occupational", "organic", "pediatric", "persistent",
    "postoperative", "postpartum", "pre-existing", "primary",
    "progressive", "proliferative", "purulent", "reactive",
    "recurrent", "refractory", "resistant", "rheumatic", "rheumatoid",
    "secondary", "senile", "septic", "specified", "suppurative",
    "surgical", "symptomatic", "systemic", "toxic", "traumatic",
    "tuberculous", "unilateral", "unspecified", "vascular", "viral",
}

QUALIFIERS = {
    "displaced", "nondisplaced", "complete", "incomplete", "partial",
    "open", "closed", "superficial", "deep", "traumatic", "nontraumatic",
    "atraumatic", "pathological", "stress", "fatigue", "spontaneous",
    "recurrent", "chronic", "acute", "subacute", "malignant", "benign",
    "primary", "secondary", "major", "minor", "moderate", "mild", "severe",
    "torus", "greenstick", "transverse", "oblique", "spiral", "segmental",
    "comminuted", "periprosthetic", "supracondylar", "physeal",
    "anterior", "posterior", "lateral", "medial", "superior", "inferior",
    "cutaneous", "subcutaneous", "epidural", "subdural", "subarachnoid",
    "penetrating", "crushing", "unspecified", "other",
}

LATERALITY = {"right", "left", "bilateral", "unspecified"}


def contains_anatomy(title: str) -> bool:
    """Check if any anatomy term appears in the title."""
    for anat in ANATOMY_TERMS:
        if anat in title:
            return True
    return False


def contains_condition_noun(title: str) -> str:
    """Return the condition noun found, or empty string."""
    words = set(title.split())
    for cn in CONDITION_NOUNS_HIGH:
        if cn in words:
            return cn
    for cn in CONDITION_NOUNS_LOW:
        if cn in words:
            return cn
    return ""


ANATOMY_TERMS_COMMA = {
    "shoulder", "elbow", "wrist", "hand", "hip", "knee",
    "ankle", "foot", "finger", "thumb", "toe", "thigh",
    "forearm", "arm", "leg", "neck", "back", "head",
    "eye", "ear", "eyelid", "scalp", "face", "buttock",
    "breast", "nose", "mouth", "groin", "perineum",
    "vertebrae", "vertebra", "pelvis", "sites", "site",
    "femur", "patella", "humerus", "radius", "ulna", "tibia",
    "fibula", "calcaneus", "scapula", "clavicle", "sacrum",
    "joint", "bone", "muscle", "tendon", "skin",
    "cornea", "retina", "lens", "iris", "sclera", "conjunctiva",
    "orbit", "macula", "mastoid",
    "palm", "region", "side", "area", "abdomen", "thorax",
    "digit", "phalanx", "spleen", "liver", "kidney", "lung",
    "intestine", "colon", "rectum", "bladder", "urethra",
    "prostate", "ovary", "testis", "penis", "scrotum",
    "cervix", "uterus", "vagina", "vulva",
    "larynx", "pharynx", "trachea", "esophagus",
    "heart", "brain", "spleen", "pancreas",
    "gallbladder", "duodenum",
    "toenail", "fingernail", "nail",
    "lip", "tongue", "tonsil", "sinus",
    "chin", "forehead", "temple", "trunk",
    "flank", "axilla", "chest",
}


def ends_with_comma_anatomy(title: str) -> bool:
    """Check if title ends with ', [laterality]? [anatomy]'."""
    m = re.search(r",\s+(right\s+|left\s+|bilateral\s+|unspecified\s+)?(\w+)\s*$", title)
    if m:
        return m.group(2).lower() in ANATOMY_TERMS_COMMA
    return False


def has_compound_match(title: str) -> bool:
    """Check if the title matches a compound condition+anatomy pattern."""
    base = strip_encounter_suffix(title)

    # Pattern: condition_noun + anatomy (via "of" or comma)
    cn = contains_condition_noun(base)
    if cn and contains_anatomy(base):
        return True

    # Pattern: [condition], [laterality]? [anatomy] (comma-separated)
    if cn and ends_with_comma_anatomy(base):
        return True

    # Pattern: [anything], [laterality]? [anatomy] where left side has medical content
    if ends_with_comma_anatomy(base):
        left_part = re.sub(r",\s+\w+\s*$", "", base).strip()
        if has_morphological_match(left_part) or contains_condition_noun(left_part):
            return True
        for w in left_part.split():
            if w in MEDICAL_ADJECTIVES or w in QUALIFIERS:
                return True

    # Pattern: condition_adjective + anatomy
    words = base.split()
    for w in words:
        if w in CONDITION_ADJECTIVES and contains_anatomy(base):
            return True

    # Pattern: medical_adj + condition_noun
    for w in words:
        if w in MEDICAL_ADJECTIVES and contains_condition_noun(base):
            return True

    # Pattern: qualifier + condition_noun
    for w in words:
        if w in QUALIFIERS and contains_condition_noun(base):
            return True

    return False


STRUCTURAL_PATTERNS = [
    re.compile(r"^toxic\b"),
    re.compile(r"^poisoning\b"),
    re.compile(r"^adverse effect\b"),
    re.compile(r"^underdosing\b"),
    re.compile(r"^maternal\b"),
    re.compile(r"^encounter for\b"),
    re.compile(r"^(personal|family) history of\b"),
    re.compile(r"^supervision of\b"),
    re.compile(r"^(newborn|neonatal)\b"),
    re.compile(r"^congenital\b"),
    re.compile(r"\w+-induced\b"),
    re.compile(r"^(blister|superficial foreign body|external constriction|insect bite)\b"),
    re.compile(r"^other\s+\w"),  # "other [condition]" is standard ICD pattern
    re.compile(r"^asphyxiation\b"),
    re.compile(r"^(retained|foreign body)\b"),
    re.compile(r"^presence of\b"),
    re.compile(r"^contact with\b"),
    re.compile(r"^(anaphylactic|anaphylactoid)\b"),
    re.compile(r"^pain\b"),
    re.compile(r"^fetal\b"),
    re.compile(r"^(preterm|premature)\b"),
    re.compile(r"^continuing pregnancy\b"),
    re.compile(r"coma\s+scale"),
    re.compile(r"^nihss\b"),
    re.compile(r"trimester$"),  # pregnancy with trimester qualifier
    re.compile(r"\btrimester\b.*\b(pregnancy|puerperium|labor|delivery)\b"),
    re.compile(r"^labor\b"),
    re.compile(r"\bpuerperium\b"),
    re.compile(r"\bintractable\b"),  # epilepsy with intractable
    re.compile(r"\bstatus epilepticus\b"),
    re.compile(r"\bwithout (behavioral|psychotic|mood)\b"),  # F-code qualifiers
    re.compile(r"^(breakdown|displacement|leakage|obstruction|perforation|protrusion|exposure|extrusion|malposition) (of|mechanical)\b"),
    re.compile(r"^(long|short) term.*\b(drug|medication|insulin)\b"),
    re.compile(r"^body mass index\b"),
    re.compile(r"^(abnormal|elevated|low|decreased|increased)\s+(level|finding|result|reading)\b"),
    re.compile(r"^abnormal\s+\w"),
]


def has_structural_match(title: str) -> bool:
    """Check if the title matches a structural/template pattern."""
    for pat in STRUCTURAL_PATTERNS:
        if pat.search(title):
            return True
    return False


def classify_title(title: str, specific_conditions: Set[str]) -> str:
    """Classify how a title would be matched. Returns match type or 'uncovered'."""
    base = strip_encounter_suffix(title)
    base_stripped = re.sub(r",\s*(right|left|bilateral|unspecified)\s*$", "", base).strip()
    base_stripped = base_stripped.rstrip(",").strip()

    # Check specific conditions (flat dictionary match)
    if base in specific_conditions or base_stripped in specific_conditions:
        return "specific"

    # Check morphological
    if has_morphological_match(title):
        return "morphological"

    # Check compound (condition + anatomy patterns)
    if has_compound_match(title):
        return "compound"

    # Check structural template patterns (toxic, poisoning, maternal, etc.)
    if has_structural_match(title):
        return "structural"

    # Check if the title ends with ", unspecified" and the base is a known condition
    if ", unspecified" in title:
        pre_unspec = title.split(", unspecified")[0].strip()
        if pre_unspec in specific_conditions:
            return "specific"
        if has_morphological_match(pre_unspec):
            return "morphological"
        if has_compound_match(pre_unspec):
            return "compound"

    # Check if any single word is a condition noun
    words = set(title.split())
    if words & CONDITION_NOUNS_HIGH:
        return "condition_noun_standalone"

    return "uncovered"


def main():
    print("Loading titles...")
    titles = load_official_titles()
    print(f"  {len(titles)} official titles (excluding external causes)")

    # Build specific conditions set from CSV (category-level + frequent phrases)
    print("\nBuilding specific conditions set...")
    specific_conditions = set()
    phrase_counter = Counter()

    for code, term in titles:
        base = strip_encounter_suffix(term)
        base = re.sub(r",\s*(right|left|bilateral|unspecified)\s*$", "", base).strip()
        base = base.rstrip(",").strip()
        if base:
            phrase_counter[base] += 1
        # 3-char category titles
        if len(code) == 3 and 2 <= len(term.split()) <= 10:
            specific_conditions.add(term)
        # 4-char subcategory titles
        if len(code) == 4 and 2 <= len(term.split()) <= 8:
            specific_conditions.add(term)

    for phrase, count in phrase_counter.items():
        if count >= 2 and len(phrase) > 6 and 2 <= len(phrase.split()) <= 6:
            specific_conditions.add(phrase)

    print(f"  {len(specific_conditions)} specific conditions in dictionary")

    # Classify all titles
    print("\nClassifying titles...")
    match_types = Counter()
    chapter_coverage = defaultdict(lambda: {"covered": 0, "total": 0})
    uncovered = []

    for code, term in titles:
        chapter = code[0]
        chapter_coverage[chapter]["total"] += 1

        mtype = classify_title(term, specific_conditions)
        match_types[mtype] += 1

        if mtype != "uncovered":
            chapter_coverage[chapter]["covered"] += 1
        else:
            uncovered.append((code, term))

    # Report
    total = len(titles)
    covered = total - match_types["uncovered"]
    print(f"\n{'='*60}")
    print(f"COVERAGE SUMMARY")
    print(f"{'='*60}")
    print(f"Total titles:     {total:>8}")
    print(f"Covered:          {covered:>8} ({100*covered/total:.1f}%)")
    print(f"Uncovered:        {match_types['uncovered']:>8} ({100*match_types['uncovered']/total:.1f}%)")

    print(f"\nBy match type:")
    for mtype, count in match_types.most_common():
        print(f"  {mtype:30s} {count:>8} ({100*count/total:.1f}%)")

    print(f"\nBy ICD chapter:")
    for ch in sorted(chapter_coverage.keys()):
        d = chapter_coverage[ch]
        pct = 100 * d["covered"] / d["total"] if d["total"] > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"  {ch}: {d['covered']:>6}/{d['total']:<6} ({pct:5.1f}%) {bar}")

    # Analyze uncovered titles
    print(f"\nUncovered title analysis ({len(uncovered)} titles):")
    print("-" * 40)

    # First words of uncovered
    first_words = Counter(t.split()[0] for _, t in uncovered)
    print("\nMost common first words in uncovered titles:")
    for word, count in first_words.most_common(30):
        print(f"  {word:30s} {count:>5}")

    # Short uncovered titles
    short_uncovered = [(c, t) for c, t in uncovered if len(t.split()) <= 3]
    print(f"\nShort uncovered titles (1-3 words): {len(short_uncovered)}")
    for c, t in sorted(short_uncovered)[:50]:
        print(f"  {c}: {t}")

    # Last words of uncovered (potential missing condition nouns)
    last_words = Counter()
    for _, t in uncovered:
        base = strip_encounter_suffix(t)
        words = base.split()
        if words:
            last_words[words[-1]] += 1
    print(f"\nMost common last words in uncovered titles:")
    for word, count in last_words.most_common(30):
        print(f"  {word:30s} {count:>5}")

    # Write uncovered to file for further analysis
    uncovered_path = Path("uncovered_titles.txt")
    with open(uncovered_path, "w") as f:
        for code, term in sorted(uncovered):
            f.write(f"{code}\t{term}\n")
    print(f"\nFull uncovered list written to {uncovered_path}")


if __name__ == "__main__":
    main()
