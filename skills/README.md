# Project Chimera — Agent Skills

> **Ref:** `ProjectChimeraTheAgenticInfrastructureChallenge.md` Task 2.3  
> **Definition:** A "Skill" is a specific, atomic capability package that a Chimera Agent
> can invoke during task execution. Skills are composable, reusable, and MCP-routed.

---

## Skill vs. MCP Tool

| Concept      | Scope                                                                                           | Example                    |
| ------------ | ----------------------------------------------------------------------------------------------- | -------------------------- |
| **Skill**    | An agent capability composed of one or more MCP tool calls, LLM reasoning, and validation logic | `skill_content_generation` |
| **MCP Tool** | A single atomic external action exposed by an MCP server                                        | `post_tweet`               |

Skills orchestrate tools. A skill may call multiple tools in sequence, apply persona
constraints, and return a confidence-scored result to the Judge.

---

## Registered Skills

### 1. `skill_content_generation`

**Purpose:** Generate platform-native text content aligned with the agent's persona.  
**Spec Ref:** `specs/functional.md` AI-007, FR 3.0

#### Input Contract

```python
{
    "prompt": str,               # What to generate
    "persona_voice": list[str],  # Voice traits from SOUL.md (e.g., ["witty", "gen-z"])
    "platform": str,             # Target: "twitter" | "instagram" | "threads"
    "max_length": int,           # Platform character limit (default: 280)
    "language": str,             # ISO 639-1 code: "en", "am" (Amharic)
}
```

#### Output Contract

```python
{
    "content": str,              # The generated text
    "confidence_score": float,   # 0.0-1.0 for Judge routing (NFR 1.0)
    "language": str,             # Language of the generated content
    "character_count": int,      # Length validation for platform limits
}
```

#### MCP Tools Used

- Cognitive Core (LLM) for text generation
- `mcp-server-weaviate.search_memory` for RAG context retrieval

---

### 2. `skill_trend_analysis`

**Purpose:** Detect emerging topic clusters in a region over a configurable time window.  
**Spec Ref:** `specs/functional.md` AI-006, FR 2.2

#### Input Contract

```python
{
    "region": str,               # Geographic region (e.g., "ethiopia")
    "time_window_hours": int,    # Analysis window (default: 4)
    "categories": list[str],     # Optional filters: ["fashion", "tech", "crypto"]
    "min_cluster_size": int,     # Minimum related topics to form a trend (default: 3)
}
```

#### Output Contract

```python
{
    "trends": [
        {
            "topic": str,                # Trend name
            "relevance_score": float,    # 0.0-1.0 relevance to agent goals
            "related_topics": list[str], # Cluster members
            "volume": int,               # Approximate mention count
        }
    ],
    "region": str,
    "analysis_window_hours": int,
    "generated_at": str,          # ISO 8601 timestamp
}
```

#### MCP Tools Used

- `mcp-server-twitter.get_trends` for trend data
- `mcp-server-news.get_headlines` for news aggregation
- Cognitive Core (LLM) for semantic clustering

---

### 3. `skill_image_consistency`

**Purpose:** Validate that a generated image matches the agent's canonical visual identity.  
**Spec Ref:** `specs/functional.md` AI-008, FR 3.1

#### Input Contract

```python
{
    "generated_image_url": str,  # URL of the newly generated image
    "reference_image_id": str,   # ID for the canonical character reference
    "agent_id": str,             # Chimera Agent being validated
}
```

#### Output Contract

```python
{
    "is_consistent": bool,       # True if images match
    "confidence": float,         # 0.0-1.0 model confidence
    "reasoning": str,            # Explanation for audit trail
}
```

#### MCP Tools Used

- `mcp-server-gemini.analyze_images` (Gemini 3 Flash Vision)
- Falls back to HITL on failure (safety-first principle)

---

## Adding a New Skill

1. Create a directory: `skills/skill_name/`
2. Add `__init__.py` with the skill function signature
3. Define Input/Output contracts as Pydantic models
4. Update this README with the interface documentation
5. Add corresponding tests in `tests/test_skills_interface.py`
6. Reference the relevant spec IDs from `specs/functional.md`
