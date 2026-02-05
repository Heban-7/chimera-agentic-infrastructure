"""
Project Chimera — Canonical Data Schemas

The authoritative Pydantic models for Task and Result objects that flow
through the Planner → Worker → Judge pipeline. These models are the
code-level implementation of specs/technical.md §2.1 and §2.2.

Spec References:
    - specs/technical.md: §2.1 (Task Object), §2.2 (Result Object)
    - SRS: §6.2 (Data Models & Schemas)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Task Schema — Spec Ref: specs/technical.md §2.1
# =============================================================================


VALID_TASK_TYPES = {
    "generate_content",
    "reply_comment",
    "execute_transaction",
    "deploy_token",
    "trend_analysis",
    "image_generation",
    "video_generation",
    "memory_update",
}

VALID_PRIORITIES = {"critical", "high", "medium", "low"}

VALID_TASK_STATUSES = {
    "pending",
    "in_progress",
    "review",
    "approved",
    "rejected",
    "complete",
    "failed",
    "human_review",
}


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
    """

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str
    priority: str = "medium"
    agent_id: str = ""
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
        if v not in VALID_TASK_TYPES:
            raise ValueError(f"task_type must be one of {VALID_TASK_TYPES}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_TASK_STATUSES:
            raise ValueError(f"status must be one of {VALID_TASK_STATUSES}")
        return v


# =============================================================================
# Result Schema — Spec Ref: specs/technical.md §2.2
# =============================================================================


class ResultArtifact(BaseModel):
    """Artifact block for a ChimeraResult. Spec Ref: specs/technical.md §2.2"""

    content_type: str
    body: str
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationLog(BaseModel):
    """Audit log entry for a tool invocation."""

    tool_name: str
    server_name: str
    latency_ms: int = 0
    success: bool = True


class ChimeraResult(BaseModel):
    """
    The artifact from Worker → Judge.
    Spec Ref: specs/technical.md §2.2
    """

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    agent_id: str
    worker_id: str
    status: str = "success"
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reasoning_trace: str = Field(..., min_length=10)
    artifact: ResultArtifact
    sensitive_topics_detected: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_version_at_start: int = Field(..., ge=0)
    execution_duration_ms: int = Field(default=0, ge=0)
    tools_invoked: list[ToolInvocationLog] = Field(default_factory=list)
