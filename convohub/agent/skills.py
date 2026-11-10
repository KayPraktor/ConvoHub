"""Skills: folders with a SKILL.md. Name + description go into the prompt; the full text is read on demand."""

import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass
class Skill:
    name: str
    description: str
    path: Path  # the SKILL.md file


def _field(block: str, key: str) -> str:
    m = re.search(rf"^{key}\s*:\s*(.+?)\s*$", block, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def discover(folders: list[str]) -> list[Skill]:
    """Find <folder>/SKILL.md and <folder>/<skill>/SKILL.md."""
    found: dict[str, Skill] = {}
    for folder in folders:
        root = Path(folder)
        candidates = [root / "SKILL.md"] + sorted(root.glob("*/SKILL.md"))
        for md in candidates:
            if not md.is_file():
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            fm = _FRONTMATTER.match(text)
            block = fm.group(1) if fm else ""
            name = _field(block, "name") or md.parent.name
            desc = _field(block, "description")
            if not desc:
                body = text[fm.end():] if fm else text
                desc = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), "")
            found.setdefault(name, Skill(name=name, description=desc[:300], path=md))
    return list(found.values())


def prompt_block(skills: list[Skill]) -> str:
    if not skills:
        return ""
    lines = ["Available skills (call read_skill with the name to get full instructions before using one):"]
    lines += [f"- {s.name}: {s.description}" for s in skills]
    return "\n".join(lines)


def read_skill(skills: list[Skill], name: str) -> str:
    for s in skills:
        if s.name == name:
            text = s.path.read_text(encoding="utf-8", errors="replace")
            others = [p.name for p in s.path.parent.iterdir() if p.name != "SKILL.md"][:50]
            extra = f"\n\n[Other files in this skill folder ({s.path.parent.as_posix()}): {', '.join(others)}]" if others else ""
            return f"[Skill '{name}' from {s.path.as_posix()}]\n{text}{extra}"
    raise KeyError(name)
