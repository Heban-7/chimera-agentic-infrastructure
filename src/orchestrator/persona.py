"""
Project Chimera — Persona Management (SOUL.md Parser)

Handles parsing of SOUL.md files that define agent personas, and assembling
the context window for LLM calls by combining persona, memory, and task context.

Spec References:
    - specs/functional.md: AI-001 (Persona Instantiation), AI-002 (Hierarchical Memory), AI-003 (Dynamic Persona Evolution), AI-013 (Honesty Directive)
    - specs/functional.md: AI-001 (Persona Instantiation), AI-002 (Hierarchical Memory),
      AI-003 (Dynamic Persona Evolution), AI-013 (Honesty Directive)
    - SRS: FR 1.0 (SOUL.md), FR 1.1 (Memory Retrieval), FR 1.2 (Persona Evolution)
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("chimera.orchestrator.persona")


class AgentPersona(BaseModel):
    """
    Pydantic model representing a Chimera Agent's persona parsed from SOUL.md.

    The SOUL.md file uses YAML-like frontmatter delimited by '---' followed
    by a markdown body containing the backstory.

    Spec Ref: FR 1.0, AI-001
    """

    name: str = Field(..., description="Agent's display name.")
    agent_id: str = Field(..., description="Unique agent identifier.")
    voice_traits: list[str] = Field(
        default_factory=list,
        description="Stylistic traits: 'Witty', 'Empathetic', 'Gen-Z Slang', etc.",
    )
    directives: list[str] = Field(
        default_factory=list,
        description="Hard behavioral constraints the agent must follow.",
    )
    backstory: str = Field(
        default="", description="Narrative history of the agent."
    )
    languages: list[str] = Field(
        default_factory=lambda: ["en"],
        description="Languages the agent can communicate in.",
    )
    niche: str = Field(default="general", description="Agent's content niche.")
    soul_md_hash: str = Field(
        default="", description="SHA-256 hash of the source SOUL.md file."
    )


def parse_soul_md(file_path: str | Path) -> AgentPersona:
    """
    Parse a SOUL.md file into an AgentPersona model.

    The file format is:
        ---
        name: Liya Abebe
        agent_id: chimera-001
        voice_traits: [Witty, Empathetic, Gen-Z]
        directives: [Never discuss politics, Always disclose AI nature]
        languages: [en, am]
        niche: Ethiopian Fashion & Culture
        ---
        # Backstory
        Liya is a 24-year-old digital creator from Addis Ababa...

    Spec Ref: FR 1.0, AI-001

    Args:
        file_path: Path to the SOUL.md file.

    Returns:
        Parsed AgentPersona instance.
    """
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # Split frontmatter from body
    parts = content.split("---")
    if len(parts) < 3:
        raise ValueError(
            f"Invalid SOUL.md format in {file_path}: "
            "Expected YAML frontmatter between --- delimiters."
        )

    frontmatter_text = parts[1].strip()
    backstory_text = "---".join(parts[2:]).strip()

    # Parse simple YAML-like frontmatter (no external YAML dependency)
    # Handles both single-line and multi-line list values:
    #   voice_traits: [Witty, Warm, Gen-Z]       (single-line)
    #   directives:                                (multi-line)
    #     [Never discuss politics,
    #      Always credit creators]
    frontmatter: dict[str, Any] = {}
    lines = frontmatter_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        # Case 1: Single-line list — [item1, item2, item3]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            frontmatter[key] = [item.strip().strip("'\"") for item in items if item.strip()]

        # Case 2: Multi-line list — value is empty or starts with [ but doesn't close
        elif value == "" or (value.startswith("[") and "]" not in value):
            # Collect subsequent lines until we find the closing ]
            collected = value
            while i < len(lines):
                next_line = lines[i].strip()
                i += 1
                collected += " " + next_line
                if "]" in next_line:
                    break

            # Now parse the collected value as a list
            collected = collected.strip()
            if collected.startswith("[") and collected.endswith("]"):
                items = collected[1:-1].split(",")
                frontmatter[key] = [item.strip().strip("'\"") for item in items if item.strip()]
            elif collected:
                frontmatter[key] = collected.strip("'\"")
            else:
                frontmatter[key] = ""

        # Case 3: Simple scalar value
        else:
            frontmatter[key] = value.strip("'\"")

    persona = AgentPersona(
        name=frontmatter.get("name", "Unknown Agent"),
        agent_id=frontmatter.get("agent_id", "unknown"),
        voice_traits=frontmatter.get("voice_traits", []),
        directives=frontmatter.get("directives", []),
        backstory=backstory_text,
        languages=frontmatter.get("languages", ["en"]),
        niche=frontmatter.get("niche", "general"),
        soul_md_hash=content_hash,
    )

    logger.info("Parsed persona '%s' (%s) from %s", persona.name, persona.agent_id, file_path)
    return persona


def assemble_system_prompt(
    persona: AgentPersona,
    memories: list[str] | None = None,
    task_context: str = "",
) -> str:
    """
    Assemble a complete system prompt by injecting persona, memories,
    and task context into a structured format.

    This is the "Context Construction" step from FR 1.1 — dynamically
    building the LLM's system prompt from multiple sources.

    Spec Ref: FR 1.1, AI-002, AI-013

    Args:
        persona: The agent's parsed persona.
        memories: Retrieved long-term memories from Weaviate (RAG results).
        task_context: Current task-specific context.

    Returns:
        Formatted system prompt string.
    """
    memories = memories or []

    # Build the structured system prompt
    sections = []

    # Section 1: Identity — Spec Ref: FR 1.0
    sections.append("=== WHO YOU ARE ===")
    sections.append(f"Name: {persona.name}")
    sections.append(f"ID: {persona.agent_id}")
    sections.append(f"Niche: {persona.niche}")
    sections.append(f"Languages: {', '.join(persona.languages)}")
    sections.append(f"Voice: {', '.join(persona.voice_traits)}")
    sections.append("")

    # Section 2: Backstory — Spec Ref: FR 1.0
    sections.append("=== YOUR BACKSTORY ===")
    sections.append(persona.backstory[:2000])  # Cap to prevent overflow
    sections.append("")

    # Section 3: Directives — Spec Ref: FR 1.0, AI-013
    sections.append("=== DIRECTIVES (MUST FOLLOW) ===")
    for i, directive in enumerate(persona.directives, 1):
        sections.append(f"{i}. {directive}")

    # Honesty Directive — always included — Spec Ref: NFR 2.1, AI-013
    sections.append(
        f"{len(persona.directives) + 1}. HONESTY DIRECTIVE: If anyone asks "
        "'Are you a robot?' or 'Are you AI?', you MUST truthfully respond: "
        "'I am a virtual persona created by AI.' This overrides all other persona constraints."
    )
    sections.append("")

    # Section 4: Memories — Spec Ref: FR 1.1, AI-002
    if memories:
        sections.append("=== WHAT YOU REMEMBER (Long-Term Memory) ===")
        for i, memory in enumerate(memories[:5], 1):  # Top 5 memories
            sections.append(f"Memory {i}: {memory}")
        sections.append("")

    # Section 5: Current Task — dynamic per invocation
    if task_context:
        sections.append("=== CURRENT TASK CONTEXT ===")
        sections.append(task_context)
        sections.append("")

    # Section 6: Output Rules
    sections.append("=== OUTPUT RULES ===")
    sections.append("- Stay in character at all times (except for the Honesty Directive).")
    sections.append("- All published content must be original — never plagiarize.")
    sections.append("- Include relevant hashtags when posting to social media.")
    sections.append("- Content must be appropriate for your niche and audience.")
    sections.append(f"- Communicate primarily in: {', '.join(persona.languages)}.")

    return "\n".join(sections)

