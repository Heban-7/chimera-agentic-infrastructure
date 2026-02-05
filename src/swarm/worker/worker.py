"""
Project Chimera — Worker Agent (The Executor)

This module implements the "Worker" role of the FastRender Swarm pattern.
Workers are stateless, ephemeral agents designed to execute a single atomic
task with maximum focus and speed.

Spec References:
    - specs/functional.md: AI-007 (Multimodal Generation), AI-010 (MCP Publishing),
      AI-011 (Bi-directional Loop), AI-012 (AI Disclosure)
    - specs/technical.md: §2.1 (Task Schema), §2.2 (Result Schema), §5.2 (Queues)
    - SRS: §3.1.2 (The Worker), FR 6.0
    - research/architecture_strategy.md: §The Worker (Executor)

Implementation Status: SCAFFOLD — Awaiting spec ratification for full implementation.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("chimera.swarm.worker")


# =============================================================================
# Worker Result Model — Spec Ref: specs/technical.md §2.2
# =============================================================================


class WorkerResult(BaseModel):
    """
    The artifact produced by a Worker after executing a task.
    Pushed to the review_queue for Judge evaluation.

    Spec Ref: specs/technical.md §2.2 (Result Object)
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
    The Executor: Stateless, ephemeral agents that pop tasks from the
    TaskQueue, execute them using MCP tools, and push results to
    the ReviewQueue.

    Spec Ref:
        - SRS §3.1.2 (The Worker)
        - specs/functional.md AI-007 through AI-012
        - research/architecture_strategy.md §The Worker (Executor)

    Design Principles:
        - Shared-nothing architecture (no peer communication) — SRS §3.1.2
        - All external actions via MCPClient — project-chimera.mdc Rule 2
        - Every result includes confidence_score — NFR 1.0
        - AI disclosure on all published content — NFR 2.0, AI-012

    Implementation Status: SCAFFOLD
    """

    def __init__(
        self,
        worker_id: str,
        redis_client: Any,
        mcp_client: Any,
        llm_model: str = "gemini-3-flash",
    ):
        """
        Initialize a Worker instance.

        Args:
            worker_id: Unique identifier for this worker instance.
            redis_client: Async Redis client for queue operations.
            mcp_client: MCPClient for tool invocations.
            llm_model: LLM for task execution (default: Gemini 3 Flash).
                       Spec Ref: research/architecture_strategy.md §The Worker
        """
        self.worker_id = worker_id
        self.redis_client = redis_client
        self.mcp_client = mcp_client
        self.llm_model = llm_model

    async def pull_task(self, agent_id: str) -> dict[str, Any] | None:
        """
        Pop a task from the agent's Redis task queue.

        Spec Ref: specs/technical.md §5.2, §5.3

        Uses XREADGROUP for consumer group semantics, ensuring
        at-least-once delivery under Addis Ababa network conditions.

        Args:
            agent_id: The Chimera Agent whose queue to consume.

        Returns:
            Task data dict, or None if queue is empty.
        """
        stream_key = f"chimera:task_queue:{agent_id}"
        group_name = "chimera_workers"

        try:
            # XREADGROUP for at-least-once delivery
            # Block for up to 5 seconds (Addis resilience: short block)
            # Spec Ref: specs/technical.md §5.3
            messages = await self.redis_client.xreadgroup(
                groupname=group_name,
                consumername=self.worker_id,
                streams={stream_key: ">"},
                count=1,
                block=5000,
            )

            if messages:
                stream, entries = messages[0]
                msg_id, data = entries[0]
                logger.info(
                    "Worker %s pulled task %s from agent %s",
                    self.worker_id,
                    data.get("task_id"),
                    agent_id,
                )
                return {"message_id": msg_id, **data}

            return None

        except Exception as e:
            logger.error(
                "Error pulling task for agent %s: %s",
                agent_id,
                str(e),
            )
            return None

    async def execute_task(
        self,
        task: dict[str, Any],
        agent_id: str,
        state_version: int,
    ) -> WorkerResult:
        """
        Execute a single atomic task using MCP tools.

        Spec Ref: SRS §3.1.2, AI-007 through AI-012

        The Worker:
        1. Reads the task type and goal
        2. Invokes appropriate MCP tools
        3. Generates content using the LLM
        4. Packages the result with confidence_score and reasoning_trace
        5. Pushes to review_queue for Judge evaluation

        Args:
            task: Task data from the queue.
            agent_id: The owning Chimera Agent.
            state_version: Current GlobalState version for OCC.

        Returns:
            WorkerResult with the generated artifact.
        """
        start_time = time.monotonic()
        task_id = task.get("task_id", str(uuid.uuid4()))
        task_type = task.get("task_type", "generate_content")
        tools_invoked: list[dict[str, Any]] = []

        logger.info(
            "Worker %s executing task %s (type: %s) for agent %s",
            self.worker_id,
            task_id,
            task_type,
            agent_id,
        )

        try:
            # SCAFFOLD: Task execution logic dispatched by task_type
            # Each task type maps to specific MCP tool invocations
            # Spec Ref: AI-007 (content), AI-010 (publishing), AI-011 (replies)

            # Placeholder — real implementation dispatches by task_type
            artifact_body = ""
            artifact_type = "text"
            confidence_score = 0.0

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            result = WorkerResult(
                task_id=task_id,
                agent_id=agent_id,
                worker_id=self.worker_id,
                status="success",
                confidence_score=confidence_score,
                reasoning_trace=(
                    f"Task {task_type} executed by worker {self.worker_id}. "
                    f"Scaffold mode — awaiting full implementation."
                ),
                artifact_type=artifact_type,
                artifact_body=artifact_body,
                state_version_at_start=state_version,
                execution_duration_ms=elapsed_ms,
                tools_invoked=tools_invoked,
            )

            return result

        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "Worker %s failed task %s: %s",
                self.worker_id,
                task_id,
                str(e),
            )
            return WorkerResult(
                task_id=task_id,
                agent_id=agent_id,
                worker_id=self.worker_id,
                status="failed",
                confidence_score=0.0,
                reasoning_trace=f"Task execution failed: {str(e)}",
                artifact_type="text",
                artifact_body="",
                state_version_at_start=state_version,
                execution_duration_ms=elapsed_ms,
                tools_invoked=tools_invoked,
            )

    async def submit_result(
        self, agent_id: str, result: WorkerResult
    ) -> str:
        """
        Push a completed result to the agent's review queue for Judge evaluation.

        Spec Ref: specs/technical.md §5.2, §6.2

        Args:
            agent_id: The owning Chimera Agent.
            result: The completed WorkerResult.

        Returns:
            Redis stream message ID.
        """
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

        logger.info(
            "Worker %s submitted result %s to review queue for agent %s",
            self.worker_id,
            result.result_id,
            agent_id,
        )

        return msg_id

    async def run_loop(self, agent_id: str) -> None:
        """
        Main worker loop: pull → execute → submit → repeat.

        Spec Ref: SRS §3.1.2, FR 6.0

        Runs indefinitely until cancelled. Uses asyncio for non-blocking
        operation per project-chimera.mdc Rule 3.
        """
        logger.info(
            "Worker %s starting loop for agent %s",
            self.worker_id,
            agent_id,
        )

        while True:
            try:
                task = await self.pull_task(agent_id)

                if task is None:
                    # No tasks available — wait before retrying
                    # Spec Ref: project-chimera.mdc Rule 3 (asyncio.sleep)
                    await asyncio.sleep(1.0)
                    continue

                # Get current state version for OCC
                state_key = f"chimera:state_version:{agent_id}"
                version_raw = await self.redis_client.get(state_key)
                state_version = int(version_raw) if version_raw else 0

                # Execute and submit
                result = await self.execute_task(task, agent_id, state_version)
                await self.submit_result(agent_id, result)

                # ACK the message after successful processing
                stream_key = f"chimera:task_queue:{agent_id}"
                msg_id = task.get("message_id")
                if msg_id:
                    await self.redis_client.xack(
                        stream_key, "chimera_workers", msg_id
                    )

            except asyncio.CancelledError:
                logger.info("Worker %s cancelled", self.worker_id)
                break
            except Exception as e:
                logger.error(
                    "Worker %s error in loop: %s",
                    self.worker_id,
                    str(e),
                )
                # Back off on error — Spec Ref: specs/technical.md §5.3
                await asyncio.sleep(5.0)
