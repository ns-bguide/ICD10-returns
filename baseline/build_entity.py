"""Build the ICD-10-CM Diagnostic Classifications Entity XML.

Reads icd10cm_terms_2026.csv and generates a comprehensive matching entity
that covers official ICD-10-CM titles through a combination of:
  - Private sub-entities (anatomy, conditions, qualifiers, etc.)
  - Compound patterns that compose sub-entities
  - Flat dictionary entries for specific/non-decomposable terms
  - Natural language variant patterns
  - False positive suppression (score=0)

External cause codes (V00-Y99) are excluded from this entity.
"""

import csv
import re
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


CSV_PATH = Path(__file__).parent / ".." / "shared" / "icd10cm_terms_2026.csv"
OUTPUT_PATH = Path(__file__).parent / "entity.xml"

EXTERNAL_CAUSE_RE = re.compile(r"^[VWXY]")


def load_official_titles() -> List[Tuple[str, str]]:
    """Return (code, term) pairs for official titles, excluding external causes."""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Type"] == "official" and not EXTERNAL_CAUSE_RE.match(row["ICD10CMCode"]):
                rows.append((row["ICD10CMCode"], row["Term"].strip()))
    return rows


def strip_encounter_suffix(title: str) -> str:
    """Remove trailing encounter/sequela suffixes."""
    title = re.sub(r",\s*(initial|subsequent)\s+encounter.*$", "", title)
    title = re.sub(r",\s*sequela(\s.*)?$", "", title)
    return title.strip()


def strip_laterality(title: str) -> str:
    """Remove trailing laterality markers."""
    title = re.sub(r",\s*(right|left|bilateral|unspecified)\s*(eye|ear|arm|leg|hand|foot|hip|knee|shoulder|elbow|wrist|ankle|thigh|forearm)?\s*$", "", title)
    return title.strip()


# ── Vocabulary extraction ──────────────────────────────────────────

ENCOUNTER_SUFFIXES = [
    "initial encounter",
    "subsequent encounter",
    "sequela",
    "initial encounter for closed fracture",
    "initial encounter for open fracture",
    "initial encounter for open fracture type i or ii",
    "initial encounter for open fracture type iiia, iiib, or iiic",
    "initial encounter for fracture",
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
    "sequela of fracture",
]

# Core anatomy terms extracted from ICD titles (frequency >= 5 in "of [anatomy]" position)
# These are the body parts/structures that appear after "of" in structured titles.
ANATOMY_CORE = sorted({
    # Skeletal
    "femur", "patella", "humerus", "radius", "ulna", "tibia", "fibula",
    "calcaneus", "talus", "metatarsal", "metacarpal bone", "scapula",
    "clavicle", "sacrum", "coccyx", "sternum", "rib", "ribs", "rib cage",
    "mandible", "skull", "vertebra", "pelvis", "pubis", "ischium", "ilium",
    "acetabulum", "xiphoid process", "manubrium", "acromial process",
    # Joints
    "hip joint", "knee joint", "ankle joint", "elbow joint", "shoulder joint",
    "wrist", "ankle", "knee", "elbow", "shoulder", "hip",
    "acromioclavicular joint", "sternoclavicular joint", "sacroiliac joint",
    "temporomandibular joint", "ulnohumeral joint",
    "first carpometacarpal joint",
    # Limbs and regions
    "arm", "forearm", "upper arm", "hand", "finger", "thumb",
    "index finger", "middle finger", "ring finger", "little finger",
    "leg", "lower leg", "thigh", "foot", "toe", "great toe",
    "lesser toe(s)", "toe(s)", "big toe",
    "head", "neck", "face", "scalp", "trunk", "back", "lower back",
    "buttock", "groin", "flank", "axilla", "perineum",
    "abdominal wall", "chest wall", "front wall of thorax", "back wall of thorax",
    "palm", "chin", "forehead", "temple",
    # Organs
    "brain", "cerebrum", "cerebellum", "brainstem", "spinal cord",
    "cervical spinal cord", "thoracic spinal cord", "lumbar spinal cord",
    "sacral spinal cord",
    "heart", "lung", "liver", "kidney", "spleen", "pancreas",
    "stomach", "duodenum", "jejunum", "ileum", "colon", "rectum",
    "appendix", "gallbladder", "esophagus", "pharynx", "larynx",
    "trachea", "bronchus", "diaphragm", "bladder", "urethra", "ureter",
    "uterus", "cervix", "ovary", "fallopian tube", "vagina", "vulva",
    "prostate", "testis", "penis", "scrotum", "epididymis",
    "thyroid", "thyroid gland", "adrenal gland", "pituitary gland",
    "thymus", "parathyroid gland",
    # Eye
    "eye", "eyelid", "cornea", "retina", "lens", "iris", "sclera",
    "choroid", "ciliary body", "optic nerve", "optic disc", "conjunctiva",
    "lacrimal gland", "globe", "vitreous body", "macula", "orbit",
    # Ear
    "ear", "inner ear", "middle ear", "external ear", "ear drum",
    "tympanic membrane", "mastoid",
    # Blood vessels
    "aorta", "carotid artery", "femoral artery", "popliteal artery",
    "tibial artery", "brachial artery", "radial artery", "ulnar artery",
    "iliac artery", "renal artery", "pulmonary artery", "coronary artery",
    "cerebral artery", "vertebral artery", "basilar artery",
    "superior mesenteric artery", "inferior mesenteric artery", "celiac artery",
    "femoral vein", "iliac vein", "renal vein", "portal vein",
    "jugular vein", "subclavian vein", "pulmonary vessels",
    "inferior vena cava", "superior vena cava",
    "greater saphenous vein", "lesser saphenous vein",
    # Nerves
    "facial nerve", "trigeminal nerve", "acoustic nerve", "cranial nerve",
    "brachial plexus", "lumbosacral plexus",
    # Soft tissue
    "muscle", "tendon", "ligament", "bursa", "synovium", "cartilage",
    "achilles tendon", "rotator cuff",
    # Skin
    "skin", "nail", "epidermis", "dermis",
    # Other structures
    "bone", "bone marrow", "joint", "artery", "vein", "nerve",
    "lymph nodes", "blood", "meninges", "peritoneum", "pleura",
    "pericardium", "endometrium", "breast", "nipple",
    "mouth", "tongue", "lip", "palate", "tonsil", "adenoids",
    "nose", "nasal bones", "sinus", "salivary gland",
    "bile duct", "bile ducts",
    # Spine specific
    "cervical vertebrae", "thoracic vertebra", "lumbar vertebra",
    "cervical intervertebral disc", "thoracic intervertebral disc",
    "lumbar intervertebral disc",
    # Compound/qualified
    "eyelid and periocular area", "upper eyelid", "lower eyelid",
    "upper extremity", "lower extremity", "upper limb", "lower limb",
    "anus", "anal canal",
    "large intestine", "small intestine",
    "external genital organs",
    "abdominal aorta", "thoracic aorta",
})

# Condition nouns that appear in ICD titles
CONDITION_NOUNS_HIGH = sorted({
    # Very common, unambiguous on their own
    "fracture", "fractures",
    "dislocation", "dislocations",
    "subluxation", "subluxations",
    "laceration", "lacerations",
    "contusion", "contusions",
    "abrasion", "abrasions",
    "sprain", "sprains",
    "strain", "strains",
    "injury", "injuries",
    "wound", "wounds",
    "hemorrhage", "hemorrhages",
    "rupture", "ruptures",
    "stenosis",
    "obstruction",
    "occlusion",
    "embolism",
    "thrombosis",
    "infarction",
    "neoplasm", "neoplasms",
    "carcinoma",
    "lymphoma",
    "melanoma",
    "leukemia",
    "sarcoma",
    "mesothelioma",
    "abscess", "abscesses",
    "ulcer", "ulcers",
    "hernia",
    "prolapse",
    "fistula",
    "cyst", "cysts",
    "polyp", "polyps",
    "gangrene",
    "necrosis",
    "fibrosis",
    "sclerosis",
    "edema",
    "effusion",
    "atrophy",
    "hypertrophy",
    "hyperplasia",
    "hypoplasia",
    "atresia",
    "ectasia",
    "degeneration",
    "calcification",
    "erosion",
    "adhesion", "adhesions",
    "perforation",
    "amputation",
    "sepsis",
    "infection", "infections",
    "inflammation",
    "syndrome",
    "disorder", "disorders",
    "disease", "diseases",
    "deficiency", "deficiencies",
    "complication", "complications",
    "malformation", "malformations",
    "deformity", "deformities",
    "insufficiency",
    "dysfunction",
    "anomaly", "anomalies",
    "lesion", "lesions",
    "tumor", "tumors",
    "cancer", "cancers",
})

# Condition nouns that are ambiguous without anatomy context
CONDITION_NOUNS_LOW = sorted({
    "burn", "burns",
    "corrosion",
    "poisoning",
    "bite", "bites",
    "sting", "stings",
    "failure",
    "compression",
    "obstruction",
    "restriction",
    "swelling",
    "tenderness",
    "weakness",
    "numbness",
    "detachment",
    "displacement",
    "breakdown",
    "fragmentation",
    "opacity",
    "ptosis",
})

# Qualifiers that precede condition nouns
CONDITION_QUALIFIERS = sorted({
    "displaced", "nondisplaced",
    "complete", "incomplete",
    "partial",
    "open", "closed",
    "superficial", "deep",
    "traumatic", "nontraumatic", "atraumatic",
    "pathological",
    "stress",
    "fatigue",
    "spontaneous",
    "recurrent",
    "chronic", "acute", "subacute",
    "malignant", "benign",
    "primary", "secondary",
    "major", "minor", "moderate",
    "mild", "severe",
    "torus",
    "greenstick",
    "transverse", "oblique", "spiral", "segmental", "comminuted",
    "periprosthetic", "perioperative", "postprocedural", "intraoperative",
    "supracondylar",
    "physeal",
    "anterior", "posterior", "lateral", "medial",
    "superior", "inferior",
    "cutaneous", "subcutaneous",
    "epidural", "subdural", "subarachnoid",
    "penetrating",
    "crushing",
    "unspecified", "other", "other specified",
})

# Condition adjectives (past-participle forms, adjectival)
CONDITION_ADJECTIVES = sorted({
    "abraded", "amputated", "broken", "bruised", "burned", "collapsed",
    "compressed", "contused", "corroded", "crushed", "deformed",
    "detached", "diseased", "dislocated", "dismembered",
    "fractured", "gangrenous", "impacted", "infected", "inflamed",
    "injured", "lacerated", "malformed", "necrotic", "obstructed",
    "occluded", "perforated", "prolapsed", "punctured", "ruptured",
    "severed", "shattered", "sprained", "stenotic", "strangulated",
    "swollen", "torn", "ulcerated",
})

# Medical descriptor adjectives
MEDICAL_ADJECTIVES = sorted({
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
})

# Laterality terms
LATERALITY = sorted({
    "right", "left", "bilateral", "unspecified",
})


def extract_single_word_medical_terms(titles: List[Tuple[str, str]]) -> List[str]:
    """Extract single-word titles that are unambiguous medical terms."""
    single = set()
    for _, term in titles:
        words = term.split()
        if len(words) == 1 and len(term) > 3:
            single.add(term.lower())
    return sorted(single)


MORPHOLOGICAL_SUFFIXES_ALL = {
    "itis", "osis", "emia", "pathy", "uria", "algia", "opia",
    "asis", "iasis", "oma", "ism", "tion",
    "phobia", "philia", "megaly", "cephaly", "phagia", "stasis",
    "plegia", "paresis", "spasm", "plasia",
    "cele", "lysis", "malacia", "ectasis",
    "dynia", "gnosia", "somnia",
    "praxia", "phasia", "phonia", "pnea", "mnesia",
    "cusis", "tonia", "kinesia", "rrhea", "rrhagia",
    "ectomy", "plasty", "scopy", "ostomy", "otomy",
}


def extract_morphological_terms(titles: List[Tuple[str, str]]) -> Dict[str, Set[str]]:
    """Extract terms by medical suffix."""
    suffixes = {s: set() for s in MORPHOLOGICAL_SUFFIXES_ALL}
    for _, term in titles:
        for word in term.split():
            word_clean = re.sub(r"[^a-z-]", "", word.lower())
            if not word_clean or len(word_clean) < 5:
                continue
            for suf in suffixes:
                if word_clean.endswith(suf) and len(word_clean) > len(suf) + 2:
                    suffixes[suf].add(word_clean)
    return suffixes


def extract_eponymous_terms(titles: List[Tuple[str, str]]) -> Set[str]:
    """Extract terms that contain possessive names (eponymous conditions)."""
    eponymous = set()
    pat = re.compile(r"[A-Z][a-z]+'s\b|[a-z]+'s\b")
    for _, term in titles:
        if "'" in term or "'" in term:
            base = strip_encounter_suffix(term)
            base = strip_laterality(base)
            if base and len(base.split()) <= 6:
                eponymous.add(base.lower())
    return eponymous


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── XML generation ─────────────────────────────────────────────────

def gen_entry(headword: str, comment: str = "") -> str:
    hw = xml_escape(headword)
    if comment:
        return f'            <entry headword="{hw}"/>  <!~~ {comment} ~~>'
    return f'            <entry headword="{hw}"/>'


def gen_entity_block(name: str, etype: str, case: str, entries: List[str],
                     patterns: List[str] = None, comment: str = "",
                     score0_patterns: List[str] = None) -> str:
    """Generate a complete entity block."""
    lines = []
    if comment:
        for cline in comment.split("\n"):
            lines.append(f"        <!-- {cline.strip()} -->")
        lines.append("")
    lines.append(f'        <entity name="{name}" type="{etype}" case="{case}">')
    lines.append("")
    if score0_patterns:
        lines.append("            <!-- False positive suppression -->")
        for pat in score0_patterns:
            lines.append(f'            <pattern score="0" case="insensitive">{xml_escape(pat)}</pattern>')
        lines.append("")
    if patterns:
        for pat in patterns:
            lines.append(f'            <pattern case="insensitive">{xml_escape(pat)}</pattern>')
        lines.append("")
    for entry in entries:
        lines.append(entry)
    lines.append("")
    lines.append("        </entity>")
    return "\n".join(lines)


def build_xml(titles: List[Tuple[str, str]]) -> str:
    """Build the complete entity XML."""

    single_words = extract_single_word_medical_terms(titles)
    morpho = extract_morphological_terms(titles)

    # Collect all unique medical terms from titles (for the_big_list equivalent)
    base_titles = set()
    for _, term in titles:
        base = strip_encounter_suffix(term)
        base = strip_laterality(base)
        base = base.strip().rstrip(",").strip()
        if base:
            base_titles.add(base.lower())

    # ── Build sub-entities ──

    sections = []

    # Header
    sections.append(textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <!--
        ICD-10-CM Diagnostic Classifications Entity
        =============================================

        Covers the majority of ICD-10-CM titles (diagnostic codes) through a
        combination of flat dictionary entries and combinatory patterns.

        SCOPE:
          - ICD-10-CM chapters A-U (diagnostic codes)
          - Official titles + natural language variants
          - Enriched forms (abbreviations, word-order variants)

        EXCLUDED:
          - External cause codes V00-Y99 (pedestrian accidents, falls, assaults,
            activities, military operations, etc.) are NOT covered by this entity.
            These require separate treatment due to their non-medical vocabulary.

        ARCHITECTURE:
          Private sub-entities compose into public matching entities:

          icd10cm/anatomy ─────────────┐
          icd10cm/condition_nouns ──────┤
          icd10cm/qualifiers ───────────┼──▶ icd10cm/compound_conditions
          icd10cm/medical_adjectives ───┤
          icd10cm/encounter_suffixes ───┘

          icd10cm/morphological_terms ──┐
          icd10cm/specific_conditions ──┼──▶ icd10cm/standalone_conditions
          icd10cm/eponymous_conditions ─┘

          Both feed into the public entity: icd10cm/diagnostic_classifications

        FALSE POSITIVES:
          Terms like "burn", "failure", "compression" are in conditions_low and
          require anatomical context. Score=0 patterns suppress known FP phrases.

        VARIANT HANDLING:
          - Abbreviations: lt/rt for left/right, chr/acu for chronic/acute, etc.
          - Word order: "fracture of femur" ↔ "femur fracture"
          - Connectors: "due to" ↔ "caused by" ↔ "because of"
          - Punctuation: hyphens, apostrophes, and/&, or//
    -->
    """))

    # ── 1. Anatomy entity ──
    anat_entries = [gen_entry(t) for t in ANATOMY_CORE]
    sections.append(gen_entity_block(
        "icd10cm/anatomy", "private", "insensitive",
        anat_entries,
        comment="Body parts, organs, and anatomical structures from ICD-10-CM titles.\n"
                "These appear in the 'of [anatomy]' position of structured titles.\n"
                "Includes qualified forms like 'cervical spinal cord' and 'thoracic aorta'."
    ))

    # ── 2. Anatomy plural ──
    anat_plural_entries = [gen_entry(t) for t in sorted({
        "arteries", "bones", "bronchi", "cells", "digits", "ducts",
        "ears", "extremities", "eyes", "eyelids", "feet", "femurs",
        "fingers", "glands", "hands", "hips", "joints", "kidneys",
        "knees", "legs", "limbs", "lungs", "lymph nodes",
        "meninges", "muscles", "nails", "nerves", "organs", "ovaries",
        "ribs", "shoulders", "sinuses", "tendons", "testes", "toes",
        "tonsils", "ureters", "veins", "vertebrae", "vessels", "wrists",
    })]
    sections.append(gen_entity_block(
        "icd10cm/anatomy_plural", "private", "insensitive",
        anat_plural_entries,
        comment="Plural forms of anatomical terms."
    ))

    # ── 3. Condition nouns (high confidence) ──
    cond_high_entries = [gen_entry(t) for t in CONDITION_NOUNS_HIGH]
    sections.append(gen_entity_block(
        "icd10cm/condition_nouns_high", "private", "insensitive",
        cond_high_entries,
        comment="Medical condition nouns that are unambiguous on their own.\n"
                "These can match independently or in combination with anatomy.\n"
                "E.g., 'fracture', 'hemorrhage', 'neoplasm', 'syndrome'."
    ))

    # ── 4. Condition nouns (low confidence - need anatomy) ──
    cond_low_entries = [gen_entry(t) for t in CONDITION_NOUNS_LOW]
    sections.append(gen_entity_block(
        "icd10cm/condition_nouns_low", "private", "insensitive",
        cond_low_entries,
        comment="Condition nouns that are ambiguous without anatomical context.\n"
                "'burn' could be 'burn the evidence', 'failure' could be 'project failure'.\n"
                "Must be paired with anatomy terms in compound patterns.\n"
                "Do NOT use these in standalone matching rules.",
        score0_patterns=[
            "burn notice", "burn rate", "burn out", "burnout",
            "total failure", "mission failure", "project failure",
            "system failure", "engine failure", "power failure",
            "market breakdown", "communication breakdown",
            "mental breakdown",
        ]
    ))

    # ── 5. Condition qualifiers ──
    qual_entries = [gen_entry(t) for t in CONDITION_QUALIFIERS]
    sections.append(gen_entity_block(
        "icd10cm/condition_qualifiers", "private", "insensitive",
        qual_entries,
        comment="Adjectives/qualifiers that precede condition nouns.\n"
                "E.g., 'displaced fracture', 'traumatic rupture', 'acute stenosis'."
    ))

    # ── 6. Condition adjectives (past participle) ──
    cadj_entries = [gen_entry(t) for t in CONDITION_ADJECTIVES]
    sections.append(gen_entity_block(
        "icd10cm/condition_adjectives", "private", "insensitive",
        cadj_entries,
        comment="Past-participle adjectives for conditions.\n"
                "E.g., 'fractured femur', 'dislocated shoulder', 'infected wound'.\n"
                "Ambiguous alone ('broken clock', 'torn paper'), require anatomy."
    ))

    # ── 7. Medical adjectives ──
    madj_entries = [gen_entry(t) for t in MEDICAL_ADJECTIVES]
    sections.append(gen_entity_block(
        "icd10cm/medical_adjectives", "private", "insensitive",
        madj_entries,
        comment="Adjectives that describe medical conditions.\n"
                "E.g., 'acute', 'chronic', 'congenital', 'malignant', 'idiopathic'.\n"
                "For use in compound patterns only."
    ))

    # ── 8. Laterality ──
    lat_entries = [gen_entry(t) for t in LATERALITY]
    sections.append(gen_entity_block(
        "icd10cm/laterality", "private", "insensitive",
        lat_entries,
        comment="Laterality markers: right, left, bilateral, unspecified."
    ))

    # ── 9. Encounter suffixes ──
    enc_entries = [gen_entry(t) for t in ENCOUNTER_SUFFIXES]
    sections.append(gen_entity_block(
        "icd10cm/encounter_suffixes", "private", "insensitive",
        enc_entries,
        comment="Encounter and sequela suffixes.\n"
                "These appear at the end of titles after a comma.\n"
                "E.g., ', initial encounter', ', subsequent encounter for fracture with nonunion'."
    ))

    # ── 10. Determiners and connectors ──
    det_entries = [gen_entry(t) for t in sorted({
        "of", "of the", "of a", "in", "in the",
        "at", "at the", "to", "to the",
        "involving", "involving the", "affecting", "affecting the",
        "due to", "caused by", "because of", "resulting from",
        "associated with", "secondary to", "complicating",
        "following", "with", "without", "and",
    })]
    sections.append(gen_entity_block(
        "icd10cm/connectors", "private", "insensitive",
        det_entries,
        comment="Prepositions, connectors, and linking words in ICD title structures.\n"
                "E.g., 'fracture OF femur', 'infection DUE TO staphylococcus'."
    ))

    # ── 11. Morphological medical terms ──
    # Collect all unique -itis, -osis, -emia, -pathy etc. terms from titles
    all_morpho = set()
    for suf_terms in morpho.values():
        all_morpho.update(suf_terms)
    # Also add single-word terms
    all_morpho.update(t.lower() for t in single_words)

    # Remove terms that are too common/ambiguous
    fp_morpho = {
        "condition", "position", "condition", "operation",
        "situation", "education", "fashion", "motion", "nation",
        "station", "location", "relation", "emotion", "promotion",
        "tradition", "commission", "permission", "admission",
    }
    all_morpho -= fp_morpho

    morpho_entries = [gen_entry(t) for t in sorted(all_morpho)]
    morpho_regex_patterns = [
        f"[a-z]{{3,}}{suf}" for suf in sorted(MORPHOLOGICAL_SUFFIXES_ALL)
        if suf not in ("tion", "ism", "oma")  # too FP-prone as regex
    ]
    sections.append(gen_entity_block(
        "icd10cm/morphological_terms", "private", "insensitive",
        morpho_entries,
        patterns=morpho_regex_patterns,
        comment="Single-word medical terms with morphological suffixes.\n"
                "Includes all single-word ICD-10-CM titles plus pattern-based matching\n"
                "for Greek/Latin medical suffixes (-itis, -osis, -emia, -pathy, etc.).\n"
                "These are generally unambiguous and safe to match standalone.",
        score0_patterns=[
            "television", "supervision", "provision", "revision",
            "admission", "permission", "commission", "transmission",
            "profession", "expression", "impression", "depression",
            "possession", "obsession", "concession", "succession",
            "aggression", "regression", "progression", "compression",
            "suppression", "oppression",
        ]
    ))

    # ── 12. Specific conditions (flat dictionary) ──
    # Multi-word ICD titles that don't decompose into condition+anatomy patterns
    specific_conditions = set()

    # Collect category-level titles (3-char codes) as they're usually good summary terms
    for code, term in titles:
        if len(code) == 3:
            t = term.lower().strip()
            if len(t.split()) >= 2 and len(t.split()) <= 10:
                specific_conditions.add(t)

    # Collect 4-char code titles too — subcategory level
    for code, term in titles:
        if len(code) == 4:
            t = term.lower().strip()
            if len(t.split()) >= 2 and len(t.split()) <= 8:
                specific_conditions.add(t)

    # Add common multi-word medical phrases from titles
    title_phrases = Counter()
    for _, term in titles:
        base = strip_encounter_suffix(term)
        base = strip_laterality(base).lower().strip().rstrip(",").strip()
        if 2 <= len(base.split()) <= 6:
            title_phrases[base] += 1

    # Add phrases that appear at least twice (established terminology)
    for phrase, count in title_phrases.items():
        if count >= 2 and len(phrase) > 6:
            specific_conditions.add(phrase)

    spec_entries = [gen_entry(t) for t in sorted(specific_conditions)]
    sections.append(gen_entity_block(
        "icd10cm/specific_conditions", "private", "insensitive",
        spec_entries,
        comment="Multi-word medical conditions from ICD-10-CM that are best matched as\n"
                "complete phrases rather than decomposed into component patterns.\n"
                "Includes category-level titles and frequently-occurring specific phrases."
    ))

    # ── 13. Abbreviation and variant patterns ──
    sections.append(gen_entity_block(
        "icd10cm/abbreviations", "private", "insensitive",
        [
            gen_entry("lt", "left"),
            gen_entry("rt", "right"),
            gen_entry("bilat", "bilateral"),
            gen_entry("dx", "diagnosis"),
            gen_entry("fx", "fracture"),
            gen_entry("hx", "history"),
            gen_entry("sx", "symptoms"),
            gen_entry("tx", "treatment"),
            gen_entry("chr", "chronic"),
            gen_entry("acu", "acute"),
            gen_entry("synd", "syndrome"),
            gen_entry("w/", "with"),
            gen_entry("w/o", "without"),
            gen_entry("s/p", "status post"),
            gen_entry("r/o", "rule out"),
            gen_entry("htn", "hypertension"),
            gen_entry("dm", "diabetes mellitus"),
            gen_entry("chf", "congestive heart failure"),
            gen_entry("copd", "chronic obstructive pulmonary disease"),
            gen_entry("gerd", "gastroesophageal reflux disease"),
            gen_entry("uti", "urinary tract infection"),
            gen_entry("cad", "coronary artery disease"),
            gen_entry("cvd", "cerebrovascular disease"),
            gen_entry("dvt", "deep vein thrombosis"),
            gen_entry("pe", "pulmonary embolism"),
            gen_entry("mi", "myocardial infarction"),
            gen_entry("tia", "transient ischemic attack"),
            gen_entry("ckd", "chronic kidney disease"),
            gen_entry("aki", "acute kidney injury"),
            gen_entry("ards", "acute respiratory distress syndrome"),
            gen_entry("sle", "systemic lupus erythematosus"),
            gen_entry("ra", "rheumatoid arthritis"),
            gen_entry("ms", "multiple sclerosis"),
            gen_entry("als", "amyotrophic lateral sclerosis"),
            gen_entry("tb", "tuberculosis"),
            gen_entry("hiv", "human immunodeficiency virus"),
            gen_entry("aids", "acquired immunodeficiency syndrome"),
            gen_entry("mrsa", "methicillin-resistant staphylococcus aureus"),
            gen_entry("afib", "atrial fibrillation"),
            gen_entry("a-fib", "atrial fibrillation"),
            gen_entry("ibs", "irritable bowel syndrome"),
            gen_entry("bph", "benign prostatic hyperplasia"),
            gen_entry("pcos", "polycystic ovary syndrome"),
            gen_entry("tbi", "traumatic brain injury"),
            gen_entry("acl", "anterior cruciate ligament"),
        ],
        comment="Common medical abbreviations and shorthand.\n"
                "These map to their expanded ICD-10-CM forms."
    ))

    # ── 14. Compound matching patterns ──
    # These are the combinatory rules that compose sub-entities
    compound_patterns = [
        # Pattern 1: [qualifier]? [condition_noun] of [laterality]? [anatomy] [, encounter]?
        "((?A:icd10cm/condition_qualifiers)\\ ){0,2}(?A:icd10cm/condition_nouns_high)"
        "\\ (?A:icd10cm/connectors)\\ ((?A:icd10cm/laterality)\\ )?"
        "(?A:icd10cm/anatomy)",

        # Pattern 2: [condition_adjective] [anatomy]
        "(?A:icd10cm/condition_adjectives)\\ "
        "((?A:icd10cm/laterality)\\ )?(?A:icd10cm/anatomy)",

        # Pattern 3: [anatomy] [condition_noun] (reversed word order)
        "((?A:icd10cm/laterality)\\ )?(?A:icd10cm/anatomy)"
        "\\ (?A:icd10cm/condition_nouns_high)",

        # Pattern 4: [medical_adj]+ [condition_noun] (of [anatomy])?
        "((?A:icd10cm/medical_adjectives)\\ ){1,3}"
        "(?A:icd10cm/condition_nouns_high)"
        "(\\ (?A:icd10cm/connectors)\\ ((?A:icd10cm/laterality)\\ )?(?A:icd10cm/anatomy))?",

        # Pattern 5: [condition_noun_low] of [anatomy] (low-confidence nouns need anatomy)
        "((?A:icd10cm/condition_qualifiers)\\ )?(?A:icd10cm/condition_nouns_low)"
        "\\ (?A:icd10cm/connectors)\\ ((?A:icd10cm/laterality)\\ )?"
        "(?A:icd10cm/anatomy)",

        # Pattern 6: [medical_adj] [morphological_term]
        "((?A:icd10cm/medical_adjectives)\\ ){1,2}(?A:icd10cm/morphological_terms)",

        # Pattern 7: [condition] with [complication/detail]
        "(?A:icd10cm/condition_nouns_high)\\ with\\ [a-z].*",

        # Pattern 8: [condition] due to [cause]
        "(?A:icd10cm/condition_nouns_high)"
        "\\ (due to|caused by|because of|resulting from|secondary to|associated with)"
        "\\ [a-z].*",

        # Pattern 9: toxic [condition] / toxic effect of [substance]
        "toxic\\ (effect\\ of\\ )?[a-z].*",

        # Pattern 10: poisoning by [drug], [intent]
        "poisoning\\ (by|due to)\\ [a-z].*",

        # Pattern 11: adverse effect of [drug]
        "adverse\\ effect\\ of\\ [a-z].*",

        # Pattern 12: underdosing of [drug]
        "underdosing\\ of\\ [a-z].*",

        # Pattern 13: maternal [condition]
        "maternal\\ (care|condition|disease|disorder|complication|infection)"
        ".*",

        # Pattern 14: [condition], unspecified
        "(?A:icd10cm/condition_nouns_high),?\\ unspecified",

        # Pattern 15: [condition], [laterality] [anatomy]
        "(?A:icd10cm/condition_nouns_high),?\\ "
        "((?A:icd10cm/laterality)\\ )?(?A:icd10cm/anatomy)",

        # Pattern 16: encounter for [purpose] (Z-code patterns)
        "encounter\\ for\\ [a-z].*",

        # Pattern 17: personal/family history of [condition]
        "(personal|family)\\ history\\ of\\ [a-z].*",

        # Pattern 18: supervision of [pregnancy type]
        "supervision\\ of\\ [a-z].*\\ pregnancy.*",

        # Pattern 19: newborn/neonatal [condition]
        "(newborn|neonatal)\\ [a-z].*",

        # Pattern 20: congenital [condition] of [anatomy]
        "congenital\\ [a-z]+\\ (of|in)\\ .*",

        # Pattern 21: drug-induced/substance-induced [condition]
        "[a-z]+-induced\\ [a-z].*",

        # Pattern 22: blister/superficial foreign body of [anatomy]
        "(blister|superficial foreign body|external constriction|insect bite)"
        "(\\ \\([a-z]+\\))?\\ of\\ ((?A:icd10cm/laterality)\\ )?"
        "(?A:icd10cm/anatomy)",

        # Pattern 23: [condition] in [context/disease]
        "(?A:icd10cm/condition_nouns_high)\\ in\\ [a-z].*",

        # Pattern 24: [condition], [laterality]? [anatomy] (comma-separated, very common in M/H codes)
        "[a-z].+,\\ ((?A:icd10cm/laterality)\\ )?(?A:icd10cm/anatomy)",

        # Pattern 25: other [condition] (standard ICD "other specified" pattern)
        "other\\ (specified\\ )?[a-z].*",

        # Pattern 26: [condition] with trimester (obstetric)
        "[a-z].*,?\\ (first|second|third|unspecified)\\ trimester",

        # Pattern 27: labor/delivery/puerperium patterns
        "(obstructed\\ )?labor\\ [a-z].*",

        # Pattern 28: device complication patterns
        "(breakdown|displacement|leakage|obstruction|perforation|protrusion|exposure"
        "|extrusion|malposition)\\ (of|mechanical)\\ [a-z].*",

        # Pattern 29: asphyxiation patterns
        "asphyxiation\\ (due to|by)\\ [a-z].*",

        # Pattern 30: retained/foreign body
        "(retained|foreign body)\\ (in|of)\\ [a-z].*",

        # Pattern 31: abnormal [finding/result]
        "abnormal\\ [a-z].*",

        # Pattern 32: epilepsy with intractable/status
        "[a-z].*\\ (intractable|not intractable)(,\\ (with|without)\\ status\\ epilepticus)?",

        # Pattern 33: presence of [device/implant]
        "presence\\ of\\ [a-z].*",

        # Pattern 34: contact with/exposure to
        "(contact\\ with|exposure\\ to)\\ [a-z].*",

        # Pattern 35: coma scale / NIHSS entries
        "(coma\\ scale|nihss\\ score)\\ [a-z0-9].*",

        # Pattern 36: body mass index
        "body\\ mass\\ index\\ [a-z0-9].*",

        # Pattern 37: long/short term drug use
        "(long|short)\\ term.*\\ (drug|medication|insulin).*",

        # Pattern 38: anaphylactic [reaction/shock]
        "(anaphylactic|anaphylactoid)\\ [a-z].*",

        # Pattern 39: mental/behavioral disorder patterns (F-codes)
        "[a-z].*\\ without\\ (behavioral|psychotic|mood)\\ disturbance.*",
    ]

    compound_score0 = [
        # Common English phrases that could match patterns
        "broken record", "broken promise", "broken heart",
        "open door", "open mind", "open question",
        "open source", "open ended",
        "acute angle", "acute accent",
        "chronic complainer",
        "primary school", "primary color", "primary key",
        "secondary school", "secondary color",
        "major league", "major key", "major label",
        "minor league", "minor key",
        "partial view", "partial credit",
        "complete set", "complete guide",
        "deep state", "deep learning", "deep dive",
        "displaced person", "displaced worker",
    ]

    sections.append(gen_entity_block(
        "icd10cm/compound_conditions", "private", "insensitive",
        [],
        patterns=compound_patterns,
        comment="Compound matching patterns that compose sub-entities.\n"
                "These handle the highly templated structure of ICD-10-CM titles:\n"
                "  [qualifier]? [condition] of [laterality]? [anatomy] [, encounter]?\n"
                "Also handles reversed word order and abbreviation forms.",
        score0_patterns=compound_score0,
    ))

    # ── 15. Public entity (the final output) ──
    public_patterns = [
        "(?A:icd10cm/morphological_terms)",
        "(?A:icd10cm/specific_conditions)",
        "(?A:icd10cm/abbreviations)",
        "(?A:icd10cm/compound_conditions)",
    ]

    public_score0 = [
        # Activity codes from Z chapter - too generic
        "activity,?\\ [a-z]+",
        # Single common words that happen to be ICD terms
        "earthquake", "flood", "hurricane", "tornado", "lightning",
        "terrorism", "electrocution", "drowning", "starvation",
        "homelessness", "unhappiness", "worries",
        "overweight", "underweight",
    ]

    sections.append(gen_entity_block(
        "icd10cm/diagnostic_classifications", "public", "insensitive",
        [],
        patterns=public_patterns,
        comment="PUBLIC ENTITY: ICD-10-CM Diagnostic Classifications\n"
                "This is the main matching entity that composes all sub-entities.\n"
                "It matches:\n"
                "  - Morphological medical terms (standalone)\n"
                "  - Specific multi-word conditions (flat dictionary)\n"
                "  - Common medical abbreviations\n"
                "  - Compound condition+anatomy patterns\n"
                "Excludes external cause codes V00-Y99.",
        score0_patterns=public_score0,
    ))

    # Close XML
    sections.append("")

    return "\n\n\n".join(sections)


def main():
    print("Loading ICD-10-CM titles...")
    titles = load_official_titles()
    print(f"  Loaded {len(titles)} official titles (excluding external causes)")

    # Stats
    unique_terms = {t.lower() for _, t in titles}
    print(f"  {len(unique_terms)} unique terms")

    single_words = extract_single_word_medical_terms(titles)
    print(f"  {len(single_words)} single-word medical terms")

    morpho = extract_morphological_terms(titles)
    total_morpho = sum(len(v) for v in morpho.values())
    print(f"  {total_morpho} morphological terms across {len(morpho)} suffix types")

    print("\nGenerating entity XML...")
    xml = build_xml(titles)

    OUTPUT_PATH.write_text(xml, encoding="utf-8")
    print(f"  Written to {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size:,} bytes")

    # Count entries and patterns
    entry_count = xml.count("<entry ")
    pattern_count = xml.count("<pattern ")
    entity_count = xml.count("<entity ")
    print(f"  {entity_count} entities, {entry_count} entries, {pattern_count} patterns")


if __name__ == "__main__":
    main()
