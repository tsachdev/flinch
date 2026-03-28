import re
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"

def load_skills(role_name: str, payload: dict) -> str:
    candidates = _discover_skills(role_name)
    selected   = _select_relevant(candidates, payload)

    if not selected:
        return ""

    print(f"  [skills] loaded {len(selected)} skill(s): "
          f"{', '.join(s['name'] for s in selected)}")

    return "\n\n---\n\n".join(s["body"] for s in selected)


def _discover_skills(role_name: str) -> list:
    skills = []

    # shared skills — available to all roles
    shared_dir = SKILLS_DIR / "shared"
    if shared_dir.exists():
        for f in sorted(shared_dir.glob("*.md")):
            skill = _parse_skill(f)
            if skill:
                skills.append(skill)

    # role-specific skills
    role_dir = SKILLS_DIR / "roles" / role_name
    if role_dir.exists():
        for f in sorted(role_dir.glob("*.md")):
            skill = _parse_skill(f)
            if skill:
                skills.append(skill)

    return skills


def _parse_skill(filepath: Path) -> dict | None:
    content = filepath.read_text()

    # extract frontmatter between --- markers
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not match:
        # no frontmatter — include as-is with filename as name
        return {
            "name":        filepath.stem,
            "description": "",
            "triggers":    [],
            "body":        content
        }

    meta_block, body = match.group(1), match.group(2).strip()
    meta = {}
    for line in meta_block.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()

    triggers = [t.strip() for t in meta.get("triggers", "").split(",") if t.strip()]

    return {
        "name":        meta.get("name", filepath.stem),
        "description": meta.get("description", ""),
        "triggers":    triggers,
        "body":        body
    }


def _select_relevant(skills: list, payload: dict) -> list:
    if not skills:
        return []

    # build a search string from payload values
    payload_text = " ".join(str(v).lower() for v in payload.values())

    selected = []
    for skill in skills:
        if not skill["triggers"]:
            # no triggers defined — always include
            selected.append(skill)
            continue
        # include if any trigger keyword appears in the payload
        if any(t.lower() in payload_text for t in skill["triggers"]):
            selected.append(skill)

    # if nothing matched, include all (better safe than empty)
    return selected if selected else skills
