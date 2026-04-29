"""Generate the false positive evaluation dataset.

Produces fp_dataset.json with three label types:
  - TP (true positives): Real ICD-10-CM titles and natural variants that SHOULD match
  - FP (false positives): Phrases that should NOT match
  - EDGE: Phrases where matching is debatable (labeled with reasoning)

The dataset is designed to stress-test entity precision, not just coverage.
Coverage is measured separately against the full ICD-10-CM CSV.

Categories of false positives tested:

  1. IMPOSSIBLE_COMBO: Valid condition + valid anatomy but medically impossible
     ("fracture of liver", "burn of femur", "hernia of cornea")

  2. DOMAIN_MISMATCH: Condition applied to wrong anatomical system
     ("cirrhosis of knee", "pneumonia of knee", "cataract of knee")

  3. COMMON_ENGLISH: Everyday phrases that contain medical-sounding words
     ("broken promise", "acute angle", "chronic complainer")

  4. PARTIAL_MEDICAL: Phrases with one medical term in non-medical context
     ("viral video", "infectious laughter", "fracture clinic")

  5. AMBIGUOUS_SHORT: Short phrases too vague without context
     ("the condition", "severe case", "left side")

  6. NEAR_MISS: Almost-medical phrases that look real but aren't ICD terms
     ("bilateral happiness", "chronic tiredness", "acute boredom")

  7. NONMEDICAL_TEXT: Completely unrelated text from non-medical domains.
     No medical words at all — tests whether the entity stays silent on
     ordinary language. Covers: news, legal, finance, technology, sports,
     cooking, education, weather, real estate, literature, and more.
     ("the court dismissed the appeal", "bitcoin rose 12 percent")

Categories 1-6 probe the boundary between medical and non-medical language.
Category 7 probes the other end: text that has nothing to do with medicine.
A well-built entity should match zero entries from category 7. If it does
match any, it means the entity contains overly generic terms that fire on
ordinary text.
"""

import json
import csv
import random
from pathlib import Path

random.seed(42)

CSV_PATH = Path(__file__).parent / "icd10cm_terms_2026.csv"
OUTPUT_PATH = Path(__file__).parent / "fp_dataset.json"


def load_sample_true_positives(n=500):
    """Sample real ICD titles as true positives."""
    officials = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Type"] == "official" and not row["ICD10CMCode"].startswith(("V", "W", "X", "Y")):
                officials.append(row["Term"].strip().lower())

    random.shuffle(officials)
    sampled = officials[:n]

    # Also add natural language variants
    variants = []
    for t in sampled[:100]:
        # Word order variant: "fracture of femur" -> "femur fracture"
        if " of " in t:
            parts = t.split(" of ", 1)
            variants.append(f"{parts[1].strip()}, {parts[0].strip()}")
        # Abbreviation variant
        t2 = t.replace("left", "lt").replace("right", "rt")
        if t2 != t:
            variants.append(t2)

    return [{"text": t, "label": "TP", "category": "official_title"} for t in sampled] + \
           [{"text": t, "label": "TP", "category": "natural_variant"} for t in variants[:100]]


# ── FALSE POSITIVES ────────────────────────────────────────────────

IMPOSSIBLE_COMBOS = [
    # Fractures only apply to bones/cartilage, not organs
    ("fracture of liver", "fracture is skeletal; liver is a solid organ"),
    ("fracture of lung", "fracture is skeletal; lung is a parenchymal organ"),
    ("fracture of brain", "fracture is skeletal; brain is neural tissue"),
    ("fracture of kidney", "fracture is skeletal; kidney is a solid organ"),
    ("fracture of spleen", "fracture is skeletal; spleen is a solid organ"),
    ("fracture of bladder", "fracture is skeletal; bladder is a hollow organ"),
    ("fracture of esophagus", "fracture is skeletal; esophagus is soft tissue"),
    ("fracture of iris", "fracture is skeletal; iris is ocular tissue"),
    ("displaced fracture of liver", "qualified fracture still impossible for organs"),
    ("nondisplaced fracture of stomach", "qualified fracture still impossible for organs"),
    ("stress fracture of heart", "stress fracture is skeletal only"),
    # Dislocations only apply to joints
    ("dislocation of liver", "dislocation is joints; liver is an organ"),
    ("dislocation of kidney", "dislocation is joints; kidney is an organ"),
    ("dislocation of brain", "dislocation is joints; brain is neural"),
    ("dislocation of lung", "dislocation is joints; lung is parenchymal"),
    ("dislocation of skin", "dislocation is joints; skin is integumentary"),
    ("subluxation of liver", "subluxation is joints only"),
    ("subluxation of retina", "subluxation applies to joints not ocular tissue"),
    # Sprains only apply to ligaments/joints
    ("sprain of brain", "sprain is ligamentous; brain has no ligaments"),
    ("sprain of liver", "sprain is ligamentous; liver has no ligaments"),
    ("sprain of kidney", "sprain is ligamentous; kidney has no ligaments"),
    ("sprain of cornea", "sprain is ligamentous; cornea is ocular"),
    ("strain of patella", "strain is muscular; patella is bone"),
    ("strain of femur", "strain is muscular; femur is bone"),
    # Burns only apply to body surfaces, not internal structures
    ("burn of femur", "burn is surface; femur is internal bone"),
    ("burn of liver", "burn is surface; liver is internal organ"),
    ("burn of brain", "burn is surface; brain is internal"),
    ("burn of spinal cord", "burn is surface; spinal cord is internal"),
    ("burn of patella", "burn is surface; patella is deep bone"),
    ("burn of tibia", "burn is surface; tibia is bone"),
    ("corrosion of humerus", "corrosion is surface; humerus is bone"),
    ("corrosion of kidney", "corrosion is surface; kidney is internal"),
    # Hernias only apply to specific cavities/openings
    ("hernia of cornea", "hernia is cavity/opening; cornea is ocular surface"),
    ("hernia of skull", "hernia is cavity/opening; skull is flat bone"),
    ("hernia of patella", "hernia is cavity/opening; patella is bone"),
    ("hernia of finger", "hernia is cavity/opening; finger is extremity"),
    # Prolapse applies to organs that can descend, not bones
    ("prolapse of skull", "prolapse is organ descent; skull is bone"),
    ("prolapse of femur", "prolapse is organ descent; femur is bone"),
    ("prolapse of patella", "prolapse is organ descent; patella is bone"),
    # Embolism/thrombosis are vascular, not bone/surface
    ("embolism of nail", "embolism is vascular; nail is integumentary"),
    ("thrombosis of diaphragm", "thrombosis is vascular; diaphragm is muscle"),
    ("thrombosis of skin", "thrombosis is vascular; skin is integumentary"),
    # Cataracts/glaucoma are ocular only
    ("cataract of knee", "cataract is ocular only"),
    ("glaucoma of elbow", "glaucoma is ocular only"),
    ("retinopathy of femur", "retinopathy is ocular only"),
    # Pregnancy conditions + non-reproductive anatomy
    ("ectopic pregnancy of knee", "pregnancy is reproductive system only"),
    ("abortion of knee", "abortion is reproductive only"),
    ("placental disorder of femur", "placental is reproductive only"),
    # Dental conditions + non-dental anatomy
    ("dental caries of femur", "dental applies to teeth only"),
    ("periodontal disease of knee", "periodontal applies to teeth only"),
    # Gangrene of structures that don't undergo necrosis this way
    ("gangrene of lens", "lens doesn't undergo gangrene"),
    ("gangrene of cornea", "cornea doesn't undergo gangrene"),
]

DOMAIN_MISMATCH = [
    # Skeletal conditions on soft tissue
    ("osteoporosis of muscle", "osteoporosis is bone disease"),
    ("osteoporosis of skin", "osteoporosis is bone disease"),
    ("scoliosis of kidney", "scoliosis is spinal deformity"),
    ("kyphosis of liver", "kyphosis is spinal deformity"),
    # Neurological conditions on bone
    ("neuropathy of femur", "neuropathy is neural condition"),
    ("encephalopathy of knee", "encephalopathy is brain condition"),
    ("myelopathy of skin", "myelopathy is spinal cord condition"),
    # Hepatic conditions on non-liver
    ("cirrhosis of knee", "cirrhosis is liver condition"),
    ("hepatitis of femur", "hepatitis is liver condition"),
    # Renal conditions on non-kidney
    ("nephritis of shoulder", "nephritis is kidney condition"),
    ("nephrotic syndrome of elbow", "nephrotic is kidney condition"),
    # Cardiac conditions on non-heart
    ("arrhythmia of femur", "arrhythmia is cardiac"),
    ("myocardial infarction of knee", "MI is cardiac"),
    # Pulmonary conditions on non-lung
    ("pneumonia of knee", "pneumonia is pulmonary"),
    ("emphysema of shoulder", "emphysema is pulmonary"),
    # Dermatological conditions on bone
    ("dermatitis of femur", "dermatitis is skin condition"),
    ("psoriasis of tibia", "psoriasis is skin condition"),
]

COMMON_ENGLISH = [
    ("broken promise", "broken is condition_adjective; promise is not anatomy"),
    ("broken record", "everyday expression"),
    ("broken heart", "metaphorical, not medical"),
    ("open door", "open is qualifier; door is not anatomy"),
    ("open mind", "metaphorical"),
    ("open question", "everyday expression"),
    ("open source", "technology term"),
    ("acute angle", "geometry term"),
    ("acute accent", "linguistics term"),
    ("acute observation", "everyday expression"),
    ("chronic complainer", "everyday expression"),
    ("chronic issue", "non-medical use of chronic"),
    ("chronic underperformance", "non-medical use"),
    ("malignant influence", "metaphorical use"),
    ("benign neglect", "political term"),
    ("primary school", "education"),
    ("primary color", "art/science"),
    ("primary key", "database term"),
    ("secondary school", "education"),
    ("major league", "sports"),
    ("major label", "music industry"),
    ("minor key", "music term"),
    ("minor league", "sports"),
    ("displaced person", "refugee term"),
    ("displaced worker", "employment term"),
    ("partial view", "perspective term"),
    ("partial credit", "education term"),
    ("complete guide", "book/manual"),
    ("complete set", "collection term"),
    ("deep state", "political term"),
    ("deep learning", "AI/ML term"),
    ("deep dive", "figurative expression"),
    ("superficial analysis", "non-medical use"),
    ("lateral thinking", "non-medical use"),
    ("anterior motive", "not a thing but could pattern-match"),
    ("bilateral agreement", "diplomatic term"),
    ("compression socks", "product, not condition"),
    ("burn rate", "finance term"),
    ("burn notice", "TV show / intelligence term"),
    ("total failure", "general expression"),
    ("system failure", "technology term"),
    ("engine failure", "mechanical term"),
    ("mission failure", "general expression"),
    ("market breakdown", "finance term"),
    ("communication breakdown", "general expression"),
    ("mental breakdown", "colloquial, not ICD term"),
    ("viral video", "internet culture"),
    ("viral marketing", "business term"),
    ("infectious enthusiasm", "figurative"),
    ("infectious laughter", "figurative"),
    ("contagious enthusiasm", "figurative"),
    ("toxic relationship", "colloquial psychology"),
    ("toxic masculinity", "social term"),
    ("toxic workplace", "colloquial"),
    ("inflammatory rhetoric", "figurative"),
    ("inflammatory article", "figurative"),
    ("terminal velocity", "physics term"),
    ("terminal illness", "EDGE - this IS medical"),
    ("progressive tax", "finance term"),
    ("progressive rock", "music genre"),
    ("recurrent theme", "literary term"),
    ("degenerative art", "art criticism"),
    ("congenital liar", "figurative expression"),
    ("hereditary title", "nobility/politics"),
    ("genetic algorithm", "computer science"),
    ("immune to criticism", "figurative"),
    ("resistant to change", "figurative"),
    ("acute shortage", "economic term"),
    ("chronic shortage", "economic term"),
]

PARTIAL_MEDICAL = [
    ("the fracture was severe", "fracture in sentence context, not ICD title"),
    ("she has a condition", "condition alone is meaningless"),
    ("treatment for the disease", "disease alone is too vague"),
    ("pain in his shoulder", "EDGE - could be ICD R-code match"),
    ("numbness and weakness", "symptoms without anatomy context"),
    ("infection control", "process term, not condition"),
    ("injury prevention", "process term"),
    ("disease management", "process term"),
    ("cancer screening", "process term"),
    ("fracture clinic", "facility, not condition"),
    ("trauma center", "facility, not condition"),
    ("burn unit", "facility, not condition"),
]

AMBIGUOUS_SHORT = [
    ("left side", "laterality alone, no medical content"),
    ("right arm", "anatomy alone, no condition"),
    ("the knee", "anatomy alone"),
    ("chronic", "adjective alone"),
    ("acute", "adjective alone"),
    ("unspecified", "qualifier alone"),
    ("bilateral", "laterality alone"),
    ("fracture", "condition alone - EDGE, could be valid"),
    ("infection", "condition alone - EDGE, could be valid"),
    ("other", "qualifier alone"),
    ("type 1", "classifier alone"),
    ("type 2", "classifier alone"),
    ("with complications", "modifier alone"),
    ("not elsewhere classified", "classifier alone"),
    ("initial encounter", "encounter suffix alone"),
    ("sequela", "encounter suffix alone - EDGE, could be valid"),
]

NEAR_MISS = [
    ("bilateral happiness", "medical pattern + non-medical noun"),
    ("chronic tiredness", "medical adj + non-ICD term"),
    ("acute boredom", "medical adj + non-ICD term"),
    ("idiopathic sadness", "medical adj + non-ICD term"),
    ("congenital optimism", "medical adj + non-ICD term"),
    ("recurrent disappointment", "medical adj + non-ICD term"),
    ("familial dysfunction", "EDGE - could be medical or colloquial"),
    ("acquired taste", "non-medical use of acquired"),
    ("acquired immunity", "EDGE - IS medical concept"),
    ("progressive overload", "exercise/fitness term"),
    ("inflammatory response", "EDGE - IS medical concept"),
    ("degenerative changes", "EDGE - IS medical, vague"),
    ("autoimmune response", "EDGE - IS medical concept"),
    ("pathological liar", "colloquial use"),
    ("pathological gambling", "EDGE - IS ICD F63"),
    ("functional programming", "computer science"),
    ("functional impairment", "EDGE - IS medical concept"),
]

# ── NONMEDICAL TEXT ───────────────────────────────────────────────
# Completely unrelated text with zero medical vocabulary.
# These probe whether the entity fires on ordinary language.
# Organized by domain for clarity and maintainability.

NONMEDICAL_TEXT = [
    # ── News / current affairs ──
    ("the prime minister announced new trade agreements with neighboring countries", "news headline"),
    ("voters head to the polls amid record turnout expectations", "political news"),
    ("the committee approved the infrastructure spending bill", "legislative news"),
    ("protests erupted across the capital following the court ruling", "news report"),
    ("the ambassador was recalled after diplomatic tensions escalated", "international news"),

    # ── Legal / judicial ──
    ("the court dismissed the appeal on procedural grounds", "legal ruling"),
    ("the defendant pleaded not guilty to all charges", "court proceedings"),
    ("the jury returned a unanimous verdict after three days of deliberation", "trial outcome"),
    ("counsel for the plaintiff filed a motion to compel discovery", "legal filing"),
    ("the statute of limitations had expired before the claim was brought", "legal doctrine"),
    ("the arbitration clause in the contract was deemed enforceable", "contract law"),

    # ── Finance / economics ──
    ("bitcoin rose twelve percent in overnight trading", "cryptocurrency"),
    ("the federal reserve held interest rates steady at the quarterly meeting", "monetary policy"),
    ("quarterly earnings exceeded analyst expectations by a wide margin", "corporate finance"),
    ("the company announced a two for one stock split effective next month", "equity markets"),
    ("inflation adjusted wages have remained flat for the past decade", "economics"),
    ("the bond yield curve inverted for the third consecutive session", "fixed income"),

    # ── Technology / software ──
    ("the database migration completed without downtime", "software engineering"),
    ("the pull request was merged after passing all integration tests", "version control"),
    ("latency spikes correlated with increased cache eviction rates", "system performance"),
    ("the team adopted a microservices architecture for the new platform", "software architecture"),
    ("the API rate limit was increased from one hundred to five hundred requests per minute", "API design"),
    ("the firmware update bricked several thousand devices before it was rolled back", "hardware/software"),

    # ── Sports ──
    ("the goalkeeper saved three penalties in the shootout to win the cup", "football/soccer"),
    ("she completed the marathon in two hours and forty one minutes", "athletics"),
    ("the umpire called a controversial strike three to end the inning", "baseball"),
    ("the team clinched a playoff berth with two games remaining in the season", "general sports"),
    ("the referee awarded a free kick just outside the penalty area", "football/soccer"),

    # ── Cooking / food ──
    ("preheat the oven to three hundred seventy five degrees and line a baking sheet", "recipe instruction"),
    ("fold the egg whites gently into the batter to keep it light and airy", "baking technique"),
    ("the restaurant earned its second michelin star after a decade of consistent quality", "food review"),
    ("season the cast iron skillet and let it smoke before adding the steak", "cooking technique"),
    ("the sourdough starter needs to be fed twice daily at room temperature", "bread baking"),

    # ── Education / academia ──
    ("the curriculum was revised to include more project based learning", "education policy"),
    ("the dissertation committee requested major revisions before final approval", "academic process"),
    ("enrollment in computer science programs has doubled over the past five years", "education trends"),
    ("the professor assigned three chapters of reading for the midterm exam", "classroom instruction"),
    ("the scholarship covers tuition and housing for up to four academic years", "financial aid"),

    # ── Weather / environment ──
    ("a cold front is expected to bring heavy snowfall to the northeast by friday", "weather forecast"),
    ("temperatures will reach the upper nineties with high humidity through the weekend", "weather forecast"),
    ("the wildfire has burned over fifty thousand acres since it started last tuesday", "environmental news"),
    ("the river crested at fourteen feet above flood stage overnight", "flood reporting"),

    # ── Real estate / housing ──
    ("the three bedroom colonial on elm street sold for well above the asking price", "real estate"),
    ("mortgage rates climbed to their highest level in over two decades", "housing market"),
    ("the zoning board approved a variance for the mixed use development downtown", "urban planning"),
    ("the building inspection revealed no structural issues with the foundation", "property inspection"),

    # ── Literature / arts / culture ──
    ("the novel won the national book award for fiction in its debut year", "literary award"),
    ("the exhibition features watercolors from the artist early period in provence", "art exhibition"),
    ("the orchestra performed beethoven ninth symphony to a sold out audience", "classical music"),
    ("the documentary premiered at the sundance film festival to critical acclaim", "film"),

    # ── Transportation / logistics ──
    ("the freight train derailed near the junction but no cargo was lost", "rail transport"),
    ("flight delays cascaded across the eastern seaboard due to thunderstorms", "aviation"),
    ("the shipping container was held at customs for additional inspection", "logistics"),
    ("the city council voted to extend the subway line by three new stations", "urban transit"),

    # ── Agriculture / farming ──
    ("the wheat harvest was twenty percent below projections due to the early frost", "agriculture"),
    ("the dairy cooperative negotiated better prices for organic milk this quarter", "farming economics"),
    ("the vineyard produced its first commercial vintage after seven years of planting", "viticulture"),

    # ── Mixed everyday ──
    ("the dog chased a squirrel across the backyard and knocked over the garden chairs", "everyday life"),
    ("she finished the crossword puzzle on the train before reaching her stop", "everyday life"),
    ("the plumber replaced the corroded pipe under the kitchen sink", "home repair"),
    ("they booked a cabin in the mountains for the long weekend", "travel planning"),
    ("the library book was three weeks overdue and the fine was two dollars", "everyday life"),
    ("the landlord agreed to repaint the apartment before the new tenants moved in", "rental housing"),
]


def build_dataset():
    print("Loading true positives from ICD-10-CM titles...")
    tp_entries = load_sample_true_positives(n=500)
    print(f"  {len(tp_entries)} true positive entries")

    fp_entries = []
    for text, reason in IMPOSSIBLE_COMBOS:
        fp_entries.append({"text": text, "label": "FP", "category": "impossible_combo", "reason": reason})
    for text, reason in DOMAIN_MISMATCH:
        fp_entries.append({"text": text, "label": "FP", "category": "domain_mismatch", "reason": reason})
    for text, reason in COMMON_ENGLISH:
        if "EDGE" in reason:
            fp_entries.append({"text": text, "label": "EDGE", "category": "common_english", "reason": reason})
        else:
            fp_entries.append({"text": text, "label": "FP", "category": "common_english", "reason": reason})
    for text, reason in PARTIAL_MEDICAL:
        if "EDGE" in reason:
            fp_entries.append({"text": text, "label": "EDGE", "category": "partial_medical", "reason": reason})
        else:
            fp_entries.append({"text": text, "label": "FP", "category": "partial_medical", "reason": reason})
    for text, reason in AMBIGUOUS_SHORT:
        if "EDGE" in reason:
            fp_entries.append({"text": text, "label": "EDGE", "category": "ambiguous_short", "reason": reason})
        else:
            fp_entries.append({"text": text, "label": "FP", "category": "ambiguous_short", "reason": reason})
    for text, reason in NEAR_MISS:
        if "EDGE" in reason:
            fp_entries.append({"text": text, "label": "EDGE", "category": "near_miss", "reason": reason})
        else:
            fp_entries.append({"text": text, "label": "FP", "category": "near_miss", "reason": reason})
    for text, reason in NONMEDICAL_TEXT:
        fp_entries.append({"text": text, "label": "FP", "category": "nonmedical_text", "reason": reason})

    print(f"  {sum(1 for e in fp_entries if e['label'] == 'FP')} false positive entries")
    print(f"  {sum(1 for e in fp_entries if e['label'] == 'EDGE')} edge case entries")

    dataset = {
        "metadata": {
            "description": "ICD-10-CM entity evaluation dataset for false positive testing",
            "version": "1.0",
            "categories": {
                "impossible_combo": "Valid condition + valid anatomy but medically impossible",
                "domain_mismatch": "Condition applied to wrong anatomical system",
                "common_english": "Everyday phrases containing medical-sounding words",
                "partial_medical": "Medical term used in non-diagnostic context",
                "ambiguous_short": "Too short/vague to be meaningful matches",
                "near_miss": "Almost-medical phrases that aren't real ICD terms",
                "nonmedical_text": "Completely unrelated non-medical text from diverse domains",
                "official_title": "Real ICD-10-CM official titles (true positives)",
                "natural_variant": "Natural language variants of ICD titles (true positives)",
            },
        },
        "entries": tp_entries + fp_entries,
    }

    # Summary stats
    labels = {}
    cats = {}
    for e in dataset["entries"]:
        labels[e["label"]] = labels.get(e["label"], 0) + 1
        cats[e["category"]] = cats.get(e["category"], 0) + 1

    dataset["metadata"]["counts"] = {
        "by_label": labels,
        "by_category": cats,
        "total": len(dataset["entries"]),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\nDataset written to {OUTPUT_PATH}")
    print(f"Total entries: {len(dataset['entries'])}")
    for label, count in sorted(labels.items()):
        print(f"  {label}: {count}")


if __name__ == "__main__":
    build_dataset()
