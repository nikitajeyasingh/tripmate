"""Skill registry: discovers skills/<name>/SKILL.md and any bundled scripts.

Design mirrors Anthropic's Agent Skills pattern (progressive disclosure):
  1. Agents see only each skill's name + one-line description in their system prompt.
  2. When relevant, an agent calls `load_skill(name)` to pull in the full instructions.
  3. Skills can ship code (e.g. budget-splitter/split.py) that becomes a callable tool.
This keeps prompts small and lets new capabilities be added by dropping in a folder.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    tools: dict[str, tuple[dict, Callable[..., Any]]] = field(default_factory=dict)


def _frontmatter(text: str) -> tuple[dict, str]:
    meta: dict[str, Any] = {}
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        for line in head.strip().splitlines():
            key, _, val = line.partition(":")
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip() for v in val[1:-1].split(",") if v.strip()]
            meta[key.strip()] = val
        return meta, body.strip()
    return meta, text


class SkillRegistry:
    def __init__(self, root: Path = SKILLS_DIR):
        self.skills: dict[str, Skill] = {}
        for md in sorted(root.glob("*/SKILL.md")):
            meta, body = _frontmatter(md.read_text(encoding="utf-8"))
            skill = Skill(meta.get("name", md.parent.name), meta.get("description", ""), body)
            for script in md.parent.glob("*.py"):
                spec = importlib.util.spec_from_file_location(f"skill_{md.parent.name}_{script.stem}", script)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                schema = getattr(mod, "TOOL_SCHEMA", None)
                if schema:
                    skill.tools[schema["name"]] = (schema, getattr(mod, schema["name"]))
            self.skills[skill.name] = skill

    # ---- what agents see ------------------------------------------------- #
    def catalog(self, allowed: list[str]) -> str:
        lines = [f"- **{n}**: {self.skills[n].description}" for n in allowed if n in self.skills]
        return "Skills available (call `load_skill` to read one before using it):\n" + "\n".join(lines)

    def load_skill_schema(self, allowed: list[str]) -> dict:
        return {
            "name": "load_skill",
            "description": "Load the full instructions for one of your skills. Do this before doing work the skill covers.",
            "input_schema": {"type": "object", "properties": {"name": {"type": "string", "enum": allowed}}, "required": ["name"]},
        }

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        return s.body if s else f"Unknown skill '{name}'."

    def local_tools(self, allowed: list[str]) -> dict[str, tuple[dict, Callable[..., Any]]]:
        out: dict[str, tuple[dict, Callable[..., Any]]] = {}
        for n in allowed:
            if n in self.skills:
                out |= self.skills[n].tools
        return out
