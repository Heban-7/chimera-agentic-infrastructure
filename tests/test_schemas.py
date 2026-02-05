"""
Project Chimera — TDD Tests for Data Schema Validation

These tests validate that the Task and Result data structures conform
to the JSON schemas defined in specs/technical.md §2.1 and §2.2.

Spec References:
    - specs/technical.md: §2.1 (Task Object), §2.2 (Result Object)
    - SRS: §6.2 (Data Models & Schemas)
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing import Any, Optional


# =============================================================================
# Schema Models (Defined here to match specs/technical.md §2.1, §2.2)
# These will be moved to src/orchestrator/schemas.py during implementation.
# =============================================================================


class TaskContext(BaseModel):
    """Context block for a ChimeraTask. Spec Ref: specs/technical.md §2.1"""
    goal_description: str
    persona_constraints: list[str] = Field(default_factory=list)
    required_resources: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    budget_limit_usdc: float | None = Field(default=None, ge=0)
    character_reference_id: str | None = None


class ChimeraTask(BaseModel):
    """
    The unit of work from Planner → Worker.
    Spec Ref: specs/technical.md §2.1

    Must match the JSON Schema exactly as defined in the technical spec.
    """
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = Field(
        ...,
        description="Must be one of the allowed task types."
    )
    priority: str = Field(..., description="Execution priority.")
    agent_id: str
    context: TaskContext
    assigned_worker_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    status: str = "pending"
    state_version: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    parent_task_id: str | None = None

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: str) -> str:
        allowed = {
            "generate_content", "reply_comment", "execute_transaction",
            "deploy_token", "trend_analysis", "image_generation",
            "video_generation", "memory_update",
        }
        if v not in allowed:
            raise ValueError(f"task_type must be one of {allowed}, got '{v}'")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        allowed = {"critical", "high", "medium", "low"}
        if v not in allowed:
            raise ValueError(f"priority must be one of {allowed}, got '{v}'")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {
            "pending", "in_progress", "review", "approved",
            "rejected", "complete", "failed", "human_review",
        }
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v


class ResultArtifact(BaseModel):
    """Artifact block for a ChimeraResult. Spec Ref: specs/technical.md §2.2"""
    content_type: str
    body: str
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed = {"text", "image_url", "video_url", "transaction", "analysis"}
        if v not in allowed:
            raise ValueError(f"content_type must be one of {allowed}, got '{v}'")
        return v


class ToolInvocationLog(BaseModel):
    """Audit log entry for a tool invocation. Spec Ref: specs/technical.md §2.2"""
    tool_name: str
    server_name: str
    latency_ms: int = 0
    success: bool = True


class ChimeraResult(BaseModel):
    """
    The artifact from Worker → Judge.
    Spec Ref: specs/technical.md §2.2

    Must match the JSON Schema exactly as defined in the technical spec.
    """
    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    agent_id: str
    worker_id: str
    status: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reasoning_trace: str = Field(..., min_length=10)
    artifact: ResultArtifact
    sensitive_topics_detected: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_version_at_start: int = Field(..., ge=0)
    execution_duration_ms: int = Field(default=0, ge=0)
    tools_invoked: list[ToolInvocationLog] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def validate_result_status(cls, v: str) -> str:
        allowed = {"success", "partial", "failed"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v


# =============================================================================
# Test Category 1: Task Object Schema Validation
# Spec Ref: specs/technical.md §2.1
# =============================================================================


class TestTaskSchema:
    """Validate ChimeraTask against specs/technical.md §2.1"""

    def test_valid_task_creation(self):
        """A fully valid Task should be created successfully."""
        task = ChimeraTask(
            task_type="generate_content",
            priority="high",
            agent_id=str(uuid.uuid4()),
            context=TaskContext(
                goal_description="Generate a fashion post for Ethiopian audience",
                persona_constraints=["witty", "gen-z"],
                required_resources=["mcp://twitter/mentions/recent"],
                required_tools=["post_tweet"],
            ),
            state_version=0,
        )
        assert task.status == "pending"
        assert task.retry_count == 0
        assert task.task_type == "generate_content"

    def test_all_task_types_accepted(self):
        """All 8 task types from the spec must be accepted. Spec Ref: §2.1"""
        valid_types = [
            "generate_content", "reply_comment", "execute_transaction",
            "deploy_token", "trend_analysis", "image_generation",
            "video_generation", "memory_update",
        ]
        for tt in valid_types:
            task = ChimeraTask(
                task_type=tt,
                priority="medium",
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description=f"Test {tt}"),
            )
            assert task.task_type == tt

    def test_invalid_task_type_rejected(self):
        """Unknown task types must be rejected. Spec Ref: §2.1"""
        with pytest.raises(ValidationError):
            ChimeraTask(
                task_type="invalid_type",
                priority="high",
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description="Invalid"),
            )

    def test_all_priority_levels_accepted(self):
        """All 4 priority levels must be accepted. Spec Ref: §2.1"""
        for p in ["critical", "high", "medium", "low"]:
            task = ChimeraTask(
                task_type="generate_content",
                priority=p,
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description="Priority test"),
            )
            assert task.priority == p

    def test_invalid_priority_rejected(self):
        """Invalid priority must be rejected. Spec Ref: §2.1"""
        with pytest.raises(ValidationError):
            ChimeraTask(
                task_type="generate_content",
                priority="urgent",  # Not in spec
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description="Invalid priority"),
            )

    def test_all_statuses_accepted(self):
        """All 8 status values must be accepted. Spec Ref: §2.1"""
        statuses = [
            "pending", "in_progress", "review", "approved",
            "rejected", "complete", "failed", "human_review",
        ]
        for s in statuses:
            task = ChimeraTask(
                task_type="generate_content",
                priority="medium",
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description="Status test"),
                status=s,
            )
            assert task.status == s

    def test_state_version_must_be_non_negative(self):
        """state_version cannot be negative. Spec Ref: §2.1, FR 6.1"""
        with pytest.raises(ValidationError):
            ChimeraTask(
                task_type="generate_content",
                priority="medium",
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description="Negative version"),
                state_version=-1,
            )

    def test_retry_count_cannot_be_negative(self):
        """retry_count cannot be negative. Spec Ref: §2.1"""
        with pytest.raises(ValidationError):
            ChimeraTask(
                task_type="generate_content",
                priority="medium",
                agent_id=str(uuid.uuid4()),
                context=TaskContext(goal_description="Negative retry"),
                retry_count=-1,
            )

    def test_context_requires_goal_description(self):
        """TaskContext must have goal_description. Spec Ref: §2.1"""
        with pytest.raises(ValidationError):
            TaskContext()  # Missing required field

    def test_budget_limit_cannot_be_negative(self):
        """budget_limit_usdc must be >= 0 if provided. Spec Ref: §2.1"""
        with pytest.raises(ValidationError):
            TaskContext(
                goal_description="Negative budget",
                budget_limit_usdc=-5.0,
            )

    def test_parent_task_id_optional(self):
        """parent_task_id is optional (null). Spec Ref: §2.1"""
        task = ChimeraTask(
            task_type="generate_content",
            priority="medium",
            agent_id=str(uuid.uuid4()),
            context=TaskContext(goal_description="No parent"),
        )
        assert task.parent_task_id is None


# =============================================================================
# Test Category 2: Result Object Schema Validation
# Spec Ref: specs/technical.md §2.2
# =============================================================================


class TestResultSchema:
    """Validate ChimeraResult against specs/technical.md §2.2"""

    def test_valid_result_creation(self):
        """A fully valid Result should be created successfully."""
        result = ChimeraResult(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-001",
            status="success",
            confidence_score=0.95,
            reasoning_trace="Content generated successfully matching all persona constraints.",
            artifact=ResultArtifact(
                content_type="text",
                body="Check out the latest Ethiopian fashion!",
            ),
            state_version_at_start=0,
        )
        assert result.status == "success"
        assert result.confidence_score == 0.95

    def test_confidence_score_range(self):
        """confidence_score must be 0.0-1.0. Spec Ref: NFR 1.0"""
        with pytest.raises(ValidationError):
            ChimeraResult(
                task_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                worker_id="worker-bad",
                status="success",
                confidence_score=1.5,
                reasoning_trace="Out of range confidence.",
                artifact=ResultArtifact(content_type="text", body="test"),
                state_version_at_start=0,
            )

    def test_reasoning_trace_minimum_length(self):
        """reasoning_trace must be >= 10 chars for audit trail. Spec Ref: NFR 1.0"""
        with pytest.raises(ValidationError):
            ChimeraResult(
                task_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                worker_id="worker-short",
                status="success",
                confidence_score=0.95,
                reasoning_trace="short",
                artifact=ResultArtifact(content_type="text", body="test"),
                state_version_at_start=0,
            )

    def test_all_result_statuses_accepted(self):
        """All 3 result statuses must be accepted. Spec Ref: §2.2"""
        for s in ["success", "partial", "failed"]:
            result = ChimeraResult(
                task_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                worker_id="worker-test",
                status=s,
                confidence_score=0.80,
                reasoning_trace="Testing result status validation.",
                artifact=ResultArtifact(content_type="text", body="test"),
                state_version_at_start=0,
            )
            assert result.status == s

    def test_all_artifact_content_types_accepted(self):
        """All 5 content types must be accepted. Spec Ref: §2.2"""
        for ct in ["text", "image_url", "video_url", "transaction", "analysis"]:
            artifact = ResultArtifact(content_type=ct, body="test body")
            assert artifact.content_type == ct

    def test_invalid_content_type_rejected(self):
        """Unknown content types must be rejected. Spec Ref: §2.2"""
        with pytest.raises(ValidationError):
            ResultArtifact(content_type="audio", body="test")

    def test_tool_invocation_log_structure(self):
        """tools_invoked entries must have required fields. Spec Ref: §2.2"""
        log = ToolInvocationLog(
            tool_name="post_tweet",
            server_name="mcp-server-twitter",
            latency_ms=150,
            success=True,
        )
        assert log.tool_name == "post_tweet"

    def test_sensitive_topics_list(self):
        """sensitive_topics_detected must accept string lists. Spec Ref: NFR 1.2"""
        result = ChimeraResult(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-sensitive",
            status="success",
            confidence_score=0.95,
            reasoning_trace="Content with sensitive topics detected.",
            artifact=ResultArtifact(content_type="text", body="test"),
            sensitive_topics_detected=["politics", "health_advice"],
            state_version_at_start=0,
        )
        assert len(result.sensitive_topics_detected) == 2

    def test_result_with_full_tool_invocation_audit(self):
        """Result with complete tool audit trail. Spec Ref: §2.2"""
        result = ChimeraResult(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-audit",
            status="success",
            confidence_score=0.92,
            reasoning_trace="Full audit trail test for tool invocations.",
            artifact=ResultArtifact(
                content_type="text",
                body="Generated content",
                media_urls=["https://cdn.chimera.ai/img.png"],
                metadata={"campaign_id": "camp-001"},
            ),
            tools_invoked=[
                ToolInvocationLog(
                    tool_name="post_tweet",
                    server_name="mcp-server-twitter",
                    latency_ms=250,
                    success=True,
                ),
                ToolInvocationLog(
                    tool_name="generate_image",
                    server_name="mcp-server-ideogram",
                    latency_ms=3500,
                    success=True,
                ),
            ],
            state_version_at_start=5,
            execution_duration_ms=4200,
        )
        assert len(result.tools_invoked) == 2
        assert result.execution_duration_ms == 4200
