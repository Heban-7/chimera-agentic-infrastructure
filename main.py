"""
Project Chimera — End-to-End Pipeline Demo

Runs the complete Planner -> Worker -> Judge pipeline:
1. Loads a persona from SOUL.md
2. Planner decomposes a campaign goal into tasks (via LLM)
3. Worker executes each task (via LLM with persona context)
4. Judge evaluates each result (confidence routing + HITL check)

Usage:
    python main.py

Requires:
    - .env file with LLM_API_KEY, LLM_API_BASE_URL, LLM_MODEL

Spec Ref: SRS §3.1 (FastRender Swarm), FR 6.0 (Planner-Worker-Judge)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator.llm_client import LLMClient
from src.orchestrator.persona import parse_soul_md, assemble_system_prompt
from src.swarm.planner.planner import PlannerService, CampaignGoal
from src.swarm.worker.worker import WorkerService
from src.swarm.judge.governor import (
    Governor,
    ConfidenceScoredAction,
    ConfidenceDecision,
    HumanInterventionRequired,
    OCCConflictError,
)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("chimera.main")


def print_banner():
    """Print the Project Chimera banner."""
    print("\n" + "=" * 70)
    print("  PROJECT CHIMERA — Autonomous Influencer Pipeline Demo")
    print("  Architecture: FastRender Swarm (Planner -> Worker -> Judge)")
    print("=" * 70 + "\n")


def print_section(title: str):
    """Print a section divider."""
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}\n")


async def run_pipeline():
    """Execute the full Planner -> Worker -> Judge pipeline."""

    print_banner()

    # =========================================================================
    # Step 0: Load Persona from SOUL.md
    # Spec Ref: FR 1.0, AI-001
    # =========================================================================
    print_section("STEP 0: Loading Agent Persona (SOUL.md)")

    soul_path = Path("examples/soul_example.md")
    if not soul_path.exists():
        logger.error("SOUL.md not found at %s", soul_path)
        return

    persona = parse_soul_md(soul_path)
    print(f"  Agent: {persona.name} ({persona.agent_id})")
    print(f"  Niche: {persona.niche}")
    print(f"  Voice: {', '.join(persona.voice_traits)}")
    print(f"  Languages: {', '.join(persona.languages)}")
    print(f"  Directives: {len(persona.directives)} rules loaded")

    # Assemble the system prompt — Spec Ref: FR 1.1
    system_prompt = assemble_system_prompt(
        persona=persona,
        memories=["Previously posted about Merkato fashion week — got 2.3K likes"],
        task_context="Current campaign: Promote Ethiopian street style globally.",
    )
    print(f"  System prompt: {len(system_prompt)} chars assembled\n")

    # =========================================================================
    # Step 1: Initialize Services
    # =========================================================================
    print_section("STEP 1: Initializing Services")

    # LLM Client (OpenRouter)
    llm = LLMClient()
    print(f"  LLM: {llm.model}")
    print(f"  API: {llm.base_url}")

    # Mock Redis for demo (no live Redis required)
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="0")
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.xadd = AsyncMock(return_value="mock-stream-id")

    # Initialize Planner, Worker, Judge
    planner = PlannerService(llm_client=llm)
    worker = WorkerService(worker_id="worker-demo-001", llm_client=llm)
    judge = Governor(redis_client=mock_redis)

    print("  Planner: Ready")
    print("  Worker: worker-demo-001")
    print("  Judge/Governor: Ready (thresholds: auto>0.90, hitl>0.70)")

    # =========================================================================
    # Step 2: Planner Decomposes Campaign Goal
    # Spec Ref: MA-001, SRS §3.1.1
    # =========================================================================
    print_section("STEP 2: PLANNER — Decomposing Campaign Goal")

    goal = CampaignGoal(
        goal_description=(
            "Create a Twitter campaign promoting Ethiopian street fashion "
            "in Addis Ababa. Target Gen-Z global audience. Highlight local "
            "designers and the fusion of traditional habesha textiles with "
            "modern streetwear. Make it go viral."
        ),
        agent_id=persona.agent_id,
        priority="high",
        budget_usdc=25.0,
        target_platforms=["twitter"],
        constraints=persona.directives,
    )

    print(f"  Goal: {goal.goal_description[:100]}...")
    print(f"  Budget: ${goal.budget_usdc} USDC")
    print(f"  Calling LLM for task decomposition...\n")

    dag = await planner.decompose_goal(goal)

    print(f"  Generated {len(dag)} tasks:\n")
    for i, node in enumerate(dag, 1):
        print(f"  [{i}] {node.task_type.upper()}")
        print(f"      {node.goal_description[:80]}...")
        print(f"      Priority: {node.priority} | Est. cost: ${node.estimated_cost_usdc:.2f}")
        print()

    # =========================================================================
    # Step 3: Worker Executes Each Task
    # Spec Ref: SRS §3.1.2, AI-007
    # =========================================================================
    print_section("STEP 3: WORKER — Executing Tasks")

    results = []
    for i, node in enumerate(dag, 1):
        print(f"  Executing task [{i}/{len(dag)}]: {node.task_type}...")

        task_data = {
            "task_id": node.task_id,
            "task_type": node.task_type,
            "goal_description": node.goal_description,
            "priority": node.priority,
        }

        result = await worker.execute_task(
            task=task_data,
            agent_id=persona.agent_id,
            state_version=0,
            system_prompt=system_prompt,
        )

        results.append(result)

        # Display the result
        status_icon = "[OK]" if result.status == "success" else "[FAIL]"
        print(f"  {status_icon} Task {i}: {result.status}")
        print(f"    Confidence: {result.confidence_score:.2f}")
        print(f"    Duration: {result.execution_duration_ms}ms")

        # Show a preview of the generated content
        preview = result.artifact_body[:150].replace("\n", " ")
        print(f"    Content: {preview}...")

        if result.sensitive_topics_detected:
            print(f"    [!] Sensitive topics: {result.sensitive_topics_detected}")
        print()

    # =========================================================================
    # Step 4: Judge Reviews Each Result
    # Spec Ref: AI-017, AI-018, NFR 1.0-1.2
    # =========================================================================
    print_section("STEP 4: JUDGE — Reviewing Results")

    approved = 0
    escalated = 0
    rejected = 0

    for i, result in enumerate(results, 1):
        print(f"  Reviewing result [{i}/{len(results)}]...")

        # Convert WorkerResult to ConfidenceScoredAction for the Judge
        action = ConfidenceScoredAction(
            result_id=result.result_id,
            task_id=result.task_id,
            agent_id=result.agent_id,
            worker_id=result.worker_id,
            confidence_score=result.confidence_score,
            reasoning_trace=result.reasoning_trace,
            artifact_type=result.artifact_type,
            artifact_body=result.artifact_body,
            sensitive_topics_detected=result.sensitive_topics_detected,
            state_version_at_start=result.state_version_at_start,
        )

        # Evaluate confidence routing
        decision = judge.evaluate_confidence(action)

        if decision == ConfidenceDecision.AUTO_APPROVE:
            print(f"  [OK] AUTO-APPROVED (confidence: {result.confidence_score:.2f})")
            approved += 1
        elif decision == ConfidenceDecision.ASYNC_APPROVAL:
            reason = "sensitive topics" if result.sensitive_topics_detected else "medium confidence"
            print(f"  [HITL] ESCALATED TO HITL ({reason}, confidence: {result.confidence_score:.2f})")
            escalated += 1
        else:
            print(f"  [REJECT] REJECTED (confidence: {result.confidence_score:.2f}) -> will retry")
            rejected += 1
        print()

    # =========================================================================
    # Summary
    # =========================================================================
    print_section("PIPELINE SUMMARY")

    print(f"  Agent: {persona.name} ({persona.agent_id})")
    print(f"  Campaign: {goal.goal_description[:60]}...")
    print(f"  Tasks decomposed: {len(dag)}")
    print(f"  Tasks executed: {len(results)}")
    print(f"  Results:")
    print(f"    [OK] Auto-approved: {approved}")
    print(f"    [HITL] Escalated to HITL: {escalated}")
    print(f"    [REJECT] Rejected: {rejected}")
    print()

    # Show all generated content
    print_section("GENERATED CONTENT")
    for i, result in enumerate(results, 1):
        if result.artifact_body:
            print(f"  [{i}] ({result.confidence_score:.2f}) {result.artifact_body[:200]}")
            print()

    # Cleanup
    await llm.close()

    print("=" * 70)
    print("  Pipeline complete. Spec Ref: SRS §3.1 (FastRender Swarm)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
