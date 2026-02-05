"""
Project Chimera — Worker Agent (The Executor)

This module implements the "Worker" role of the FastRender Swarm pattern.
Workers are stateless, ephemeral agents that execute atomic tasks using
an LLM (via OpenRouter) and the agent's persona context.

Spec References:
    - specs/functional.md: AI-007 (Multimodal Generation), AI-010 (MCP Publishing),
      AI-011 (Bi-directional Loop), AI-012 (AI Disclosure)
    - specs/technical.md: §2.1 (Task Schema), §2.2 (Result Schema), §5.2 (Queues)
    - SRS: §3.1.2 (The Worker), FR 6.0
    - research/architecture_strategy.md: §The Worker (Executor)

Implementation Status: LIVE — Uses OpenRouter LLM for content generation.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("chimera.swarm.worker")


# =============================================================================
# Sensitive Topic Detection — Spec Ref: NFR 1.2
# =============================================================================

SENSITIVE_KEYWORDS: dict[str, list[str]] = {
    "politics": ["election", "political", "government", "president", "parliament", "protest", "opposition"],
    "health_advice": ["cure", "treatment", "medicine", "diagnosis", "prescription", "vaccine"],
    "financial_advice": ["invest", "guaranteed returns", "buy this stock", "financial freedom", "get rich"],
    "legal_claims": ["lawsuit", "legal action", "sue", "court order", "liable"],
}


def detect_sensitive_topics(text: str) -> list[str]:
    """Scan text for sensitive topic keywords. Spec Ref: NFR 1.2"""
    detected = []
    text_lower = text.lower()
    for topic, keywords in SENSITIVE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected.append(topic)
    return detected


# =============================================================================
# Worker Result Model — Spec Ref: specs/technical.md §2.2
# =============================================================================


class WorkerResult(BaseModel):
    """
    The artifact produced by a Worker after executing a task.
    Spec Ref: specs/technical.md §2.2
    """

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    agent_id: str
    worker_id: str
    status: str = "success"
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reasoning_trace: str = Field(..., min_length=10)
    artifact_type: str
    artifact_body: str
    media_urls: list[str] = Field(default_factory=list)
    sensitive_topics_detected: list[str] = Field(default_factory=list)
    state_version_at_start: int = Field(..., ge=0)
    execution_duration_ms: int = 0
    tools_invoked: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Worker Service — Spec Ref: SRS §3.1.2, FR 6.0
# =============================================================================


class WorkerService:
    """
    The Executor: Generates content using LLM + persona context.

    Spec Ref:
        - SRS §3.1.2 (The Worker)
        - specs/functional.md AI-007 through AI-012
        - research/architecture_strategy.md §The Worker (Executor)
    """

    def __init__(
        self,
        worker_id: str,
        llm_client: Any,
        redis_client: Any | None = None,
        mcp_client: Any | None = None,
    ):
        self.worker_id = worker_id
        self.llm_client = llm_client
        self.redis_client = redis_client
        self.mcp_client = mcp_client

    async def execute_task(
        self,
        task: dict[str, Any],
        agent_id: str,
        state_version: int,
        system_prompt: str = "",
    ) -> WorkerResult:
        """
        Execute a single atomic task using the LLM and persona context.

        Spec Ref: SRS §3.1.2, AI-007 through AI-012

        Args:
            task: Task data (task_id, task_type, goal_description, etc.).
            agent_id: The owning Chimera Agent.
            state_version: Current GlobalState version for OCC.
            system_prompt: Pre-assembled persona context from persona.py.

        Returns:
            WorkerResult with the generated artifact.
        """
        start_time = time.monotonic()
        task_id = task.get("task_id", str(uuid.uuid4()))
        task_type = task.get("task_type", "generate_content")
        goal = task.get("goal_description", "Generate content")

        logger.info(
            "Worker %s executing task %s (type: %s)",
            self.worker_id,
            task_id,
            task_type,
        )

        try:
            # Build the user prompt based on task type
            user_prompt = self._build_user_prompt(task_type, goal, task)

            # Call the LLM — Spec Ref: project-chimera.mdc Rule 3 (async)
            llm_response = await self.llm_client.generate(
                system_prompt=system_prompt or "You are a helpful content creator.",
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=1024,
            )

            content = llm_response["content"]
            latency_ms = llm_response["latency_ms"]

            # Detect sensitive topics — Spec Ref: NFR 1.2
            sensitive = detect_sensitive_topics(content)

            # Estimate confidence based on response quality
            confidence = self._estimate_confidence(content, task_type, sensitive)

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            result = WorkerResult(
                task_id=task_id,
                agent_id=agent_id,
                worker_id=self.worker_id,
                status="success",
                confidence_score=confidence,
                reasoning_trace=(
                    f"Task '{task_type}' completed in {elapsed_ms}ms. "
                    f"LLM latency: {latency_ms}ms. "
                    f"Generated {len(content)} chars of content. "
                    f"Sensitive topics: {sensitive if sensitive else 'none detected'}. "
                    f"Confidence: {confidence:.2f}."
                ),
                artifact_type="text",
                artifact_body=content,
                sensitive_topics_detected=sensitive,
                state_version_at_start=state_version,
                execution_duration_ms=elapsed_ms,
                tools_invoked=[{
                    "tool_name": "llm_generate",
                    "server_name": "openrouter",
                    "latency_ms": latency_ms,
                    "success": True,
                }],
            )

            logger.info(
                "Worker %s completed task %s (confidence: %.2f, sensitive: %s)",
                self.worker_id,
                task_id,
                confidence,
                sensitive,
            )

            return result

        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("Worker %s failed task %s: %s", self.worker_id, task_id, str(e))
            return WorkerResult(
                task_id=task_id,
                agent_id=agent_id,
                worker_id=self.worker_id,
                status="failed",
                confidence_score=0.0,
                reasoning_trace=f"Task execution failed after {elapsed_ms}ms: {str(e)}",
                artifact_type="text",
                artifact_body="",
                state_version_at_start=state_version,
                execution_duration_ms=elapsed_ms,
                tools_invoked=[],
            )

    def _build_user_prompt(
        self, task_type: str, goal: str, task: dict[str, Any]
    ) -> str:
        """Build task-specific user prompts. Spec Ref: AI-007"""

        if task_type == "generate_content":
            return (
                f"Create engaging social media content for the following goal:\n\n"
                f"{goal}\n\n"
                f"Requirements:\n"
                f"- Keep it concise (under 280 characters for Twitter)\n"
                f"- Include relevant hashtags\n"
                f"- Stay in character based on your persona\n"
                f"- Make it engaging and shareable\n"
                f"- Mark it as AI-generated content (disclosure)"
            )
        elif task_type == "trend_analysis":
            return (
                f"Analyze current trends related to:\n\n{goal}\n\n"
                f"Provide:\n"
                f"1. Top 3 trending topics in this area\n"
                f"2. Why each topic is trending\n"
                f"3. Content angle suggestions for a social media influencer\n"
                f"4. Recommended hashtags"
            )
        elif task_type == "reply_comment":
            return (
                f"Craft a thoughtful, in-character reply to this:\n\n{goal}\n\n"
                f"Requirements:\n"
                f"- Stay in persona\n"
                f"- Be authentic and engaging\n"
                f"- Keep it concise"
            )
        elif task_type == "image_generation":
            return (
                f"Write a detailed image generation prompt for:\n\n{goal}\n\n"
                f"The prompt should describe the visual in detail for an AI image generator."
            )
        else:
            return f"Execute the following task:\n\n{goal}"

    def _estimate_confidence(
        self, content: str, task_type: str, sensitive_topics: list[str]
    ) -> float:
        """
        Estimate confidence in the generated content.
        Spec Ref: NFR 1.0

        Heuristic scoring (will be replaced by LLM self-assessment in production):
        - Base: 0.85
        - Penalty for very short content: -0.15
        - Penalty for sensitive topics: -0.10 each
        - Bonus for hashtags present: +0.05
        - Cap at 0.95 (never fully auto-approve without proper validation)
        """
        confidence = 0.85

        # Penalize very short or empty content
        if len(content) < 20:
            confidence -= 0.25
        elif len(content) < 50:
            confidence -= 0.15

        # Penalize sensitive topics
        confidence -= len(sensitive_topics) * 0.10

        # Bonus for hashtags (shows awareness of platform norms)
        if "#" in content:
            confidence += 0.05

        # Cap range
        return max(0.0, min(0.95, round(confidence, 2)))

    async def submit_result(
        self, agent_id: str, result: WorkerResult
    ) -> str | None:
        """Push result to review queue. Spec Ref: specs/technical.md §5.2"""
        if self.redis_client is None:
            logger.info("No Redis — result stored in-memory only")
            return result.result_id

        stream_key = f"chimera:review_queue:{agent_id}"
        msg_id = await self.redis_client.xadd(
            stream_key,
            {
                "result_id": result.result_id,
                "task_id": result.task_id,
                "worker_id": result.worker_id,
                "status": result.status,
                "confidence_score": str(result.confidence_score),
                "reasoning_trace": result.reasoning_trace,
                "artifact_type": result.artifact_type,
                "artifact_body": result.artifact_body,
                "state_version_at_start": str(result.state_version_at_start),
            },
        )
        return msg_id
