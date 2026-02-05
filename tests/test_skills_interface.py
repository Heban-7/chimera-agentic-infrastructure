"""
Project Chimera — TDD Tests for Skills Interface Contracts

These tests verify that the skills/ modules accept the correct parameters
and return the expected output structures as defined in their READMEs.

Spec References:
    - ProjectChimeraTheAgenticInfrastructureChallenge.md: Task 2.3 (Skills Strategy)
    - specs/functional.md: AI-007 (Multimodal Generation), AI-004 (Perception)
    - skills/README.md: Interface contracts

Test Strategy:
    These tests define the "slots" that skill implementations must fill.
    They validate the interface contract (inputs, outputs, exceptions)
    without testing the actual execution (which requires MCP/API access).
"""

import pytest
from typing import Any

# =============================================================================
# Skill Interface Definitions (contracts from skills/README.md)
# These will be imported from skills/ once implemented.
# =============================================================================

# For now, we define the expected interfaces as protocol classes.
# The tests verify that any implementation matches these contracts.


class SkillInput:
    """Base class for skill input contracts."""
    pass


class SkillOutput:
    """Base class for skill output contracts."""
    pass


# --- Skill 1: Content Generation ---

class ContentGenerationInput(SkillInput):
    """Input contract for skill_content_generation.
    Spec Ref: AI-007, FR 3.0"""
    def __init__(
        self,
        prompt: str,
        persona_voice: list[str],
        platform: str,
        max_length: int = 280,
        language: str = "en",
    ):
        self.prompt = prompt
        self.persona_voice = persona_voice
        self.platform = platform
        self.max_length = max_length
        self.language = language


class ContentGenerationOutput(SkillOutput):
    """Output contract for skill_content_generation.
    Spec Ref: AI-007"""
    def __init__(
        self,
        content: str,
        confidence_score: float,
        language: str,
        character_count: int,
    ):
        self.content = content
        self.confidence_score = confidence_score
        self.language = language
        self.character_count = character_count


# --- Skill 2: Trend Analysis ---

class TrendAnalysisInput(SkillInput):
    """Input contract for skill_trend_analysis.
    Spec Ref: AI-006, FR 2.2"""
    def __init__(
        self,
        region: str,
        time_window_hours: int = 4,
        categories: list[str] | None = None,
        min_cluster_size: int = 3,
    ):
        self.region = region
        self.time_window_hours = time_window_hours
        self.categories = categories or []
        self.min_cluster_size = min_cluster_size


class TrendAnalysisOutput(SkillOutput):
    """Output contract for skill_trend_analysis.
    Spec Ref: AI-006"""
    def __init__(
        self,
        trends: list[dict[str, Any]],
        region: str,
        analysis_window_hours: int,
        generated_at: str,
    ):
        self.trends = trends
        self.region = region
        self.analysis_window_hours = analysis_window_hours
        self.generated_at = generated_at


# --- Skill 3: Image Consistency Validation ---

class ImageConsistencyInput(SkillInput):
    """Input contract for skill_image_consistency.
    Spec Ref: AI-008, FR 3.1"""
    def __init__(
        self,
        generated_image_url: str,
        reference_image_id: str,
        agent_id: str,
    ):
        self.generated_image_url = generated_image_url
        self.reference_image_id = reference_image_id
        self.agent_id = agent_id


class ImageConsistencyOutput(SkillOutput):
    """Output contract for skill_image_consistency.
    Spec Ref: AI-008"""
    def __init__(
        self,
        is_consistent: bool,
        confidence: float,
        reasoning: str,
    ):
        self.is_consistent = is_consistent
        self.confidence = confidence
        self.reasoning = reasoning


# =============================================================================
# Test Category 1: Content Generation Skill Contract
# Spec Ref: AI-007, FR 3.0
# =============================================================================


class TestContentGenerationSkill:
    """Validate the content generation skill interface.
    Spec Ref: AI-007 (Multimodal Generation), FR 3.0"""

    def test_input_requires_prompt(self):
        """Skill must require a prompt. Spec Ref: AI-007"""
        input_data = ContentGenerationInput(
            prompt="Write a tweet about Ethiopian fashion",
            persona_voice=["witty", "gen-z"],
            platform="twitter",
        )
        assert input_data.prompt is not None
        assert len(input_data.prompt) > 0

    def test_input_requires_persona_voice(self):
        """Skill must accept persona_voice constraints. Spec Ref: FR 1.0"""
        input_data = ContentGenerationInput(
            prompt="Test prompt",
            persona_voice=["empathetic", "professional"],
            platform="instagram",
        )
        assert len(input_data.persona_voice) == 2

    def test_input_accepts_all_platforms(self):
        """Skill must work across platforms. Spec Ref: FR 4.0"""
        for platform in ["twitter", "instagram", "threads"]:
            input_data = ContentGenerationInput(
                prompt="Test",
                persona_voice=["witty"],
                platform=platform,
            )
            assert input_data.platform == platform

    def test_input_default_max_length_280(self):
        """Default max_length should be 280 (Twitter limit)."""
        input_data = ContentGenerationInput(
            prompt="Test", persona_voice=["witty"], platform="twitter"
        )
        assert input_data.max_length == 280

    def test_input_supports_amharic_language(self):
        """Must support Amharic ('am') for Addis Ababa context."""
        input_data = ContentGenerationInput(
            prompt="Write in Amharic",
            persona_voice=["friendly"],
            platform="twitter",
            language="am",
        )
        assert input_data.language == "am"

    def test_output_has_confidence_score(self):
        """Output must include confidence_score for Judge routing. Spec Ref: NFR 1.0"""
        output = ContentGenerationOutput(
            content="Ethiopian fashion is fire! 🔥",
            confidence_score=0.92,
            language="en",
            character_count=32,
        )
        assert 0.0 <= output.confidence_score <= 1.0

    def test_output_has_character_count(self):
        """Output must track character_count for platform validation."""
        output = ContentGenerationOutput(
            content="Test content",
            confidence_score=0.90,
            language="en",
            character_count=12,
        )
        assert output.character_count == len(output.content)


# =============================================================================
# Test Category 2: Trend Analysis Skill Contract
# Spec Ref: AI-006, FR 2.2
# =============================================================================


class TestTrendAnalysisSkill:
    """Validate the trend analysis skill interface.
    Spec Ref: AI-006 (Trend Detection), FR 2.2"""

    def test_input_requires_region(self):
        """Skill must require a region. Spec Ref: FR 2.2"""
        input_data = TrendAnalysisInput(region="ethiopia")
        assert input_data.region == "ethiopia"

    def test_input_default_time_window_4h(self):
        """Default analysis window is 4 hours. Spec Ref: FR 2.2"""
        input_data = TrendAnalysisInput(region="ethiopia")
        assert input_data.time_window_hours == 4

    def test_input_default_min_cluster_size_3(self):
        """Trend cluster requires >= 3 related topics. Spec Ref: AI-006"""
        input_data = TrendAnalysisInput(region="ethiopia")
        assert input_data.min_cluster_size == 3

    def test_input_accepts_category_filters(self):
        """Skill must accept optional category filters."""
        input_data = TrendAnalysisInput(
            region="ethiopia",
            categories=["fashion", "tech", "crypto"],
        )
        assert len(input_data.categories) == 3

    def test_output_trends_structure(self):
        """Output trends must be a list of dicts with required fields.
        Spec Ref: AI-006"""
        output = TrendAnalysisOutput(
            trends=[
                {
                    "topic": "Ethiopian Coffee Culture",
                    "relevance_score": 0.88,
                    "related_topics": ["coffee", "ethiopia", "culture"],
                    "volume": 1500,
                },
                {
                    "topic": "Addis Ababa Tech Scene",
                    "relevance_score": 0.82,
                    "related_topics": ["tech", "startups", "addis"],
                    "volume": 900,
                },
            ],
            region="ethiopia",
            analysis_window_hours=4,
            generated_at="2026-02-05T12:00:00Z",
        )
        assert len(output.trends) == 2
        assert all("topic" in t for t in output.trends)
        assert all("relevance_score" in t for t in output.trends)

    def test_output_includes_analysis_window(self):
        """Output must report the time window used. Spec Ref: FR 2.2"""
        output = TrendAnalysisOutput(
            trends=[], region="ethiopia",
            analysis_window_hours=4, generated_at="2026-02-05T12:00:00Z",
        )
        assert output.analysis_window_hours == 4


# =============================================================================
# Test Category 3: Image Consistency Skill Contract
# Spec Ref: AI-008, FR 3.1
# =============================================================================


class TestImageConsistencySkill:
    """Validate the image consistency validation skill interface.
    Spec Ref: AI-008 (Character Consistency Lock), FR 3.1"""

    def test_input_requires_generated_image_url(self):
        """Skill must require the generated image URL. Spec Ref: FR 3.1"""
        input_data = ImageConsistencyInput(
            generated_image_url="https://cdn.chimera.ai/gen/new.png",
            reference_image_id="ref-001",
            agent_id="agent-001",
        )
        assert input_data.generated_image_url.startswith("http")

    def test_input_requires_reference_image_id(self):
        """Skill must require a reference_image_id. Spec Ref: FR 3.1"""
        input_data = ImageConsistencyInput(
            generated_image_url="https://cdn.chimera.ai/gen/new.png",
            reference_image_id="ref-001",
            agent_id="agent-001",
        )
        assert input_data.reference_image_id == "ref-001"

    def test_input_requires_agent_id(self):
        """Skill must know which agent's brand to validate against."""
        input_data = ImageConsistencyInput(
            generated_image_url="https://cdn.chimera.ai/gen/new.png",
            reference_image_id="ref-001",
            agent_id="agent-001",
        )
        assert input_data.agent_id == "agent-001"

    def test_output_is_consistent_boolean(self):
        """Output must have boolean is_consistent. Spec Ref: FR 3.1"""
        output = ImageConsistencyOutput(
            is_consistent=True,
            confidence=0.95,
            reasoning="Facial features and style match the reference.",
        )
        assert isinstance(output.is_consistent, bool)

    def test_output_confidence_in_range(self):
        """Output confidence must be 0.0-1.0."""
        output = ImageConsistencyOutput(
            is_consistent=True, confidence=0.95, reasoning="Match."
        )
        assert 0.0 <= output.confidence <= 1.0

    def test_output_includes_reasoning(self):
        """Output must include reasoning for audit trail. Spec Ref: NFR 1.0"""
        output = ImageConsistencyOutput(
            is_consistent=False,
            confidence=0.40,
            reasoning="Hair color differs significantly from reference image.",
        )
        assert len(output.reasoning) > 10
