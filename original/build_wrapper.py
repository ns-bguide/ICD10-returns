"""Create a testable wrapper around the original medical_conditions.xml.

The original file is a fragment (no root element, no public entity) containing
13 active private sub-entities. This script wraps it in a valid XML document
and adds a public entity that composes all the private entities so the
evaluator can test it.

Usage:
    python3 build_wrapper.py
"""

import re
from pathlib import Path

ORIGINAL_PATH = Path(__file__).parent / ".." / "medical_conditions.xml"
OUTPUT_PATH = Path(__file__).parent / "entity.xml"


def build():
    with open(ORIGINAL_PATH, encoding="utf-8") as f:
        content = f.read()

    # Find active (non-commented) entity names
    comment_positions = set()
    for m in re.finditer(r'<!--', content):
        start = m.start()
        end_match = re.search(r'-->', content[start:])
        if end_match:
            end = start + end_match.end()
            comment_positions.update(range(start, end))

    active_entities = []
    for m in re.finditer(r'<entity\s+name="([^"]*)"', content):
        if m.start() not in comment_positions:
            active_entities.append(m.group(1))

    print(f"Active entities in original: {len(active_entities)}")
    for name in active_entities:
        print(f"  {name}")

    # Count entries in active entities
    total_entries = len(re.findall(r'<entry\s+headword="[^"]*"', content))
    print(f"\nTotal headword entries: {total_entries}")

    # Build wrapped XML
    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append("<entities>")
    parts.append("")
    parts.append("    <!-- Original medical_conditions.xml content -->")
    parts.append(content)
    parts.append("")
    parts.append("    <!-- Public wrapper entity that composes all private sub-entities -->")
    parts.append('    <entity name="healthcare/medical_conditions" type="public" case="insensitive">')
    parts.append("        <entries/>")
    parts.append("        <patterns>")
    for name in active_entities:
        parts.append(f"            <pattern>(?A:{name})</pattern>")
    parts.append("        </patterns>")
    parts.append("    </entity>")
    parts.append("")
    parts.append("</entities>")

    xml = "\n".join(parts)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(xml)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\nWrapped entity written to {OUTPUT_PATH}")
    print(f"  File size: {size_kb:.1f} KB")
    print(f"  Active entities: {len(active_entities)} private + 1 public")


if __name__ == "__main__":
    build()
