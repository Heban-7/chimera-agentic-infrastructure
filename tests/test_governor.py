"""
Project Chimera — TDD Tests for the Governor (Judge Agent)

These tests define the "empty slots" that the Governor implementation must fill.
They SHOULD FAIL until the full implementation is wired to live Redis/DB backends.

Spec References:
    - specs/functional.md: AI-016, AI-017, AI-018, AI-019
    - specs/technical.md: §2.2 (Result Schema), §5.5 (Daily Spend Tracker)
    - research/architecture_strategy.md: §Confidence Thresholding

Test Categories:
    1. Confidence Scoring & Routing (NFR 1.0, NFR 1.1)
    2. Sensitive Topic Filter (NFR 1.2)
    3. OCC State Version Validation (FR 6.1, AI-019)
    4. Budget Check Decorator / CFO Pattern (FR 5.2, AI-016)
    5. Brand Consistency Vision Scaffold (FR 3.1, AI-008)
    6. Master Review Pipeline Integration (AI-017)
"""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.swarm.judge.governor import (
    BudgetExceededError,
    ConfidenceDecision,
    ConfidenceScoredAction,
    Governor,
    HumanInterventionRequired,
    OCCConflictError,
    TransactionProposal,
    budget_check,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock async Redis client for testing without live Redis.
    Spec Ref: specs/technical.md §5 (Redis Configuration)"""
    redis = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hset = AsyncMock()
    redis.hincrby = AsyncMock()
    redis.hincrbyfloat = AsyncMock()
    redis.get = AsyncMock(return_value="0")
    redis.xadd = AsyncMock(return_value="1234567890-0")
    return redis


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for testing without live MCP servers.
    Spec Ref: specs/technical.md §6.4"""
    client = AsyncMock()
    client.call_tool = AsyncMock(return_value={
        "is_consistent": True,
        "confidence": 0.95,
        "reasoning": "Images match in facial features and style.",
    })
    return client


@pytest.fixture
def governor(mock_redis, mock_mcp_client):
    """Create a Governor instance with mocked dependencies."""
    return Governor(
        redis_client=mock_redis,
        db_client=None,
        mcp_client=mock_mcp_client,
        auto_approve_threshold=0.90,
        hitl_threshold=0.70,
    )


@pytest.fixture
def high_confidence_action():
    """A Worker result with high confidence — should auto-approve.
    Spec Ref: NFR 1.1 (High Confidence > 0.90)"""
    return ConfidenceScoredAction(
        task_id=str(uuid.uuid4()),
        agent_id=str(uuid.uuid4()),
        worker_id="worker-001",
        confidence_score=0.95,
        reasoning_trace="Generated content matches persona voice and campaign goals. No sensitive topics detected.",
        artifact_type="text",
        artifact_body="Check out the latest Ethiopian fashion trends! #AddisStyle",
        state_version_at_start=0,
    )


@pytest.fixture
def medium_confidence_action():
    """A Worker result with medium confidence — should go to HITL.
    Spec Ref: NFR 1.1 (Medium Confidence 0.70-0.90)"""
    return ConfidenceScoredAction(
        task_id=str(uuid.uuid4()),
        agent_id=str(uuid.uuid4()),
        worker_id="worker-002",
        confidence_score=0.82,
        reasoning_trace="Content generated but tone might be slightly off-brand. Recommend review.",
        artifact_type="text",
        artifact_body="This new crypto token is gonna moon! 🚀",
        state_version_at_start=0,
    )


@pytest.fixture
def low_confidence_action():
    """A Worker result with low confidence — should be rejected.
    Spec Ref: NFR 1.1 (Low Confidence < 0.70)"""
    return ConfidenceScoredAction(
        task_id=str(uuid.uuid4()),
        agent_id=str(uuid.uuid4()),
        worker_id="worker-003",
        confidence_score=0.45,
        reasoning_trace="Content generation partially failed. Image API returned low quality result.",
        artifact_type="image_url",
        artifact_body="https://cdn.chimera.ai/generated/low_quality.png",
        state_version_at_start=0,
    )


@pytest.fixture
def sensitive_topic_action():
    """A Worker result with sensitive topics — MUST go to HITL regardless of confidence.
    Spec Ref: NFR 1.2"""
    return ConfidenceScoredAction(
        task_id=str(uuid.uuid4()),
        agent_id=str(uuid.uuid4()),
        worker_id="worker-004",
        confidence_score=0.96,  # High confidence but still must go to HITL
        reasoning_trace="Content mentions political events in Ethiopia. Flagged for review.",
        artifact_type="text",
        artifact_body="The recent political developments in Addis Ababa are reshaping the tech scene.",
        sensitive_topics_detected=["politics"],
        state_version_at_start=0,
    )


@pytest.fixture
def valid_transaction():
    """A valid transaction proposal within budget.
    Spec Ref: FR 5.2, AI-016"""
    return TransactionProposal(
        agent_id=str(uuid.uuid4()),
        to_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
        amount_usdc=5.00,
        network="base",
        purpose="Payment for graphic design services",
        confidence_score=0.97,
        reasoning_trace="Verified vendor address. Amount within budget. Service delivered.",
    )


@pytest.fixture
def over_budget_transaction():
    """A transaction that would exceed daily limit.
    Spec Ref: FR 5.2, AI-016"""
    return TransactionProposal(
        agent_id=str(uuid.uuid4()),
        to_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
        amount_usdc=45.00,
        network="base",
        purpose="Large vendor payment",
        confidence_score=0.97,
        reasoning_trace="Large payment. Budget check required.",
    )


# =============================================================================
# Test Category 1: Confidence Scoring & Routing
# Spec Ref: NFR 1.0, NFR 1.1
# =============================================================================


class TestConfidenceRouting:
    """Tests for the confidence-based HITL routing logic.
    Spec Ref: NFR 1.0 (Confidence Scoring), NFR 1.1 (Escalation Logic)"""

    def test_high_confidence_auto_approves(self, governor, high_confidence_action):
        """Confidence > 0.90 → AUTO_APPROVE. Spec Ref: NFR 1.1"""
        decision = governor.evaluate_confidence(high_confidence_action)
        assert decision == ConfidenceDecision.AUTO_APPROVE

    def test_medium_confidence_routes_to_hitl(self, governor, medium_confidence_action):
        """Confidence 0.70-0.90 → ASYNC_APPROVAL. Spec Ref: NFR 1.1"""
        decision = governor.evaluate_confidence(medium_confidence_action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_low_confidence_rejects(self, governor, low_confidence_action):
        """Confidence < 0.70 → REJECT_RETRY. Spec Ref: NFR 1.1"""
        decision = governor.evaluate_confidence(low_confidence_action)
        assert decision == ConfidenceDecision.REJECT_RETRY

    def test_exact_threshold_boundary_high(self, governor):
        """Confidence exactly at 0.90 is NOT auto-approved (must exceed).
        Spec Ref: NFR 1.1 (> 0.90 for auto-approve)"""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-boundary",
            confidence_score=0.90,
            reasoning_trace="Boundary test at exactly 0.90 threshold.",
            artifact_type="text",
            artifact_body="Test content",
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        # 0.90 is NOT > 0.90, so it falls to ASYNC_APPROVAL
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_exact_threshold_boundary_low(self, governor):
        """Confidence exactly at 0.70 is ASYNC_APPROVAL (>= 0.70).
        Spec Ref: NFR 1.1"""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-boundary-low",
            confidence_score=0.70,
            reasoning_trace="Boundary test at exactly 0.70 threshold.",
            artifact_type="text",
            artifact_body="Test content",
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_zero_confidence_rejects(self, governor):
        """Confidence 0.0 → REJECT_RETRY. Edge case."""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-zero",
            confidence_score=0.0,
            reasoning_trace="Complete failure in content generation.",
            artifact_type="text",
            artifact_body="",
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.REJECT_RETRY

    def test_perfect_confidence_auto_approves(self, governor):
        """Confidence 1.0 → AUTO_APPROVE. Edge case."""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-perfect",
            confidence_score=1.0,
            reasoning_trace="Perfect generation. All criteria met.",
            artifact_type="text",
            artifact_body="Perfect content",
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.AUTO_APPROVE


# =============================================================================
# Test Category 2: Sensitive Topic Filter
# Spec Ref: NFR 1.2
# =============================================================================


class TestSensitiveTopicFilter:
    """Tests for mandatory HITL routing on sensitive topics.
    Spec Ref: NFR 1.2 (Sensitive Topic Filters)"""

    def test_sensitive_topic_overrides_high_confidence(
        self, governor, sensitive_topic_action
    ):
        """Even with confidence 0.96, sensitive topics force HITL.
        Spec Ref: NFR 1.2"""
        decision = governor.evaluate_confidence(sensitive_topic_action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_politics_topic_forces_hitl(self, governor):
        """Political content must always go to HITL. Spec Ref: NFR 1.2"""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-politics",
            confidence_score=0.99,
            reasoning_trace="Content about political events.",
            artifact_type="text",
            artifact_body="Political content here",
            sensitive_topics_detected=["politics"],
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_health_advice_forces_hitl(self, governor):
        """Health advice content must always go to HITL. Spec Ref: NFR 1.2"""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-health",
            confidence_score=0.95,
            reasoning_trace="Content contains health advice.",
            artifact_type="text",
            artifact_body="Try this remedy for headaches!",
            sensitive_topics_detected=["health_advice"],
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_financial_advice_forces_hitl(self, governor):
        """Financial advice content must always go to HITL. Spec Ref: NFR 1.2"""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-finance",
            confidence_score=0.98,
            reasoning_trace="Content contains financial advice.",
            artifact_type="text",
            artifact_body="Invest all your money in this token!",
            sensitive_topics_detected=["financial_advice"],
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL

    def test_non_sensitive_unknown_topic_ignored(self, governor):
        """Unknown topic labels that aren't in SENSITIVE_TOPICS should not trigger HITL."""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-fashion",
            confidence_score=0.95,
            reasoning_trace="Fashion content. No sensitive topics.",
            artifact_type="text",
            artifact_body="Check out this new Ethiopian fashion line!",
            sensitive_topics_detected=["fashion"],  # Not in SENSITIVE_TOPICS
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.AUTO_APPROVE

    def test_multiple_sensitive_topics(self, governor):
        """Multiple sensitive topics detected. Spec Ref: NFR 1.2"""
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-multi",
            confidence_score=0.99,
            reasoning_trace="Content touches politics and health.",
            artifact_type="text",
            artifact_body="Political health policy update",
            sensitive_topics_detected=["politics", "health_advice"],
            state_version_at_start=0,
        )
        decision = governor.evaluate_confidence(action)
        assert decision == ConfidenceDecision.ASYNC_APPROVAL


# =============================================================================
# Test Category 3: OCC State Version Validation
# Spec Ref: FR 6.1, AI-019
# =============================================================================


class TestOCCValidation:
    """Tests for Optimistic Concurrency Control.
    Spec Ref: FR 6.1, AI-019"""

    @pytest.mark.asyncio
    async def test_matching_state_version_passes(self, governor, mock_redis):
        """State version matches → validation passes. Spec Ref: FR 6.1"""
        mock_redis.get = AsyncMock(return_value="5")
        result = await governor.validate_state_version(
            task_id="task-001",
            agent_id="agent-001",
            state_version_at_start=5,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_drifted_state_version_raises_occ_error(self, governor, mock_redis):
        """State version drifted → OCCConflictError raised. Spec Ref: FR 6.1, AI-019"""
        mock_redis.get = AsyncMock(return_value="10")
        with pytest.raises(OCCConflictError) as exc_info:
            await governor.validate_state_version(
                task_id="task-002",
                agent_id="agent-002",
                state_version_at_start=5,
            )
        assert exc_info.value.expected_version == 5
        assert exc_info.value.actual_version == 10

    @pytest.mark.asyncio
    async def test_initial_state_version_zero(self, governor, mock_redis):
        """First task ever — state version should be 0. Spec Ref: FR 6.1"""
        mock_redis.get = AsyncMock(return_value=None)  # No version set yet
        result = await governor.validate_state_version(
            task_id="task-003",
            agent_id="agent-003",
            state_version_at_start=0,
        )
        assert result is True


# =============================================================================
# Test Category 4: Budget Check Decorator / CFO Pattern
# Spec Ref: FR 5.2, AI-016
# =============================================================================


class TestBudgetCheck:
    """Tests for the @budget_check decorator and CFO financial governance.
    Spec Ref: FR 5.2 (CFO Sub-Agent), AI-016"""

    @pytest.mark.asyncio
    async def test_transaction_within_budget_succeeds(
        self, governor, mock_redis, valid_transaction
    ):
        """Transaction within daily limit should be authorized.
        Spec Ref: FR 5.2"""
        mock_redis.hget = AsyncMock(return_value="10.00")  # $10 spent so far
        with patch.dict(os.environ, {"MAX_DAILY_LIMIT_USDC": "50.0", "FINANCIAL_CONFIDENCE_THRESHOLD": "0.95"}):
            result = await governor.validate_transaction(
                proposal=valid_transaction, redis_client=mock_redis
            )
        assert result["authorized"] is True
        assert result["amount_usdc"] == 5.00

    @pytest.mark.asyncio
    async def test_transaction_exceeding_budget_raises_error(
        self, governor, mock_redis, over_budget_transaction
    ):
        """Transaction exceeding daily limit raises BudgetExceededError.
        Spec Ref: FR 5.2, AI-016"""
        mock_redis.hget = AsyncMock(return_value="20.00")  # $20 spent + $45 proposed > $50
        with patch.dict(os.environ, {"MAX_DAILY_LIMIT_USDC": "50.0", "FINANCIAL_CONFIDENCE_THRESHOLD": "0.95"}):
            with pytest.raises(BudgetExceededError) as exc_info:
                await governor.validate_transaction(
                    proposal=over_budget_transaction, redis_client=mock_redis
                )
            assert exc_info.value.daily_limit == 50.0

    @pytest.mark.asyncio
    async def test_low_confidence_transaction_raises_hitl(
        self, governor, mock_redis
    ):
        """Financial transaction with confidence < 0.95 requires HITL.
        Spec Ref: FR 5.2 (financial threshold is 0.95, higher than standard 0.90)"""
        low_conf_tx = TransactionProposal(
            agent_id=str(uuid.uuid4()),
            to_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
            amount_usdc=5.00,
            network="base",
            purpose="Payment with low confidence",
            confidence_score=0.91,  # Above standard 0.90 but below financial 0.95
            reasoning_trace="Transaction seems valid but not fully certain.",
        )
        mock_redis.hget = AsyncMock(return_value="0.00")
        with patch.dict(os.environ, {"MAX_DAILY_LIMIT_USDC": "50.0", "FINANCIAL_CONFIDENCE_THRESHOLD": "0.95"}):
            with pytest.raises(HumanInterventionRequired) as exc_info:
                await governor.validate_transaction(
                    proposal=low_conf_tx, redis_client=mock_redis
                )
            assert exc_info.value.confidence_score == 0.91

    @pytest.mark.asyncio
    async def test_budget_check_updates_redis_after_success(
        self, governor, mock_redis, valid_transaction
    ):
        """After successful transaction, Redis daily_spend must be atomically updated.
        Spec Ref: specs/technical.md §5.5"""
        mock_redis.hget = AsyncMock(return_value="0.00")
        with patch.dict(os.environ, {"MAX_DAILY_LIMIT_USDC": "50.0", "FINANCIAL_CONFIDENCE_THRESHOLD": "0.95"}):
            await governor.validate_transaction(
                proposal=valid_transaction, redis_client=mock_redis
            )
        # Verify HINCRBYFLOAT was called to update spend
        mock_redis.hincrbyfloat.assert_called_once()
        mock_redis.hincrby.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_amount_transaction_rejected_by_pydantic(self):
        """TransactionProposal with 0 amount should fail Pydantic validation.
        Spec Ref: specs/technical.md §2.2"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TransactionProposal(
                agent_id=str(uuid.uuid4()),
                to_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
                amount_usdc=0.0,  # Must be > 0
                network="base",
                purpose="Zero amount test",
                confidence_score=0.95,
                reasoning_trace="This should fail validation.",
            )

    @pytest.mark.asyncio
    async def test_first_transaction_of_day_no_prior_spend(
        self, governor, mock_redis, valid_transaction
    ):
        """First transaction of the day when no prior spend exists.
        Spec Ref: specs/technical.md §5.5"""
        mock_redis.hget = AsyncMock(return_value=None)  # No spend yet
        with patch.dict(os.environ, {"MAX_DAILY_LIMIT_USDC": "50.0", "FINANCIAL_CONFIDENCE_THRESHOLD": "0.95"}):
            result = await governor.validate_transaction(
                proposal=valid_transaction, redis_client=mock_redis
            )
        assert result["authorized"] is True


# =============================================================================
# Test Category 5: Brand Consistency Vision
# Spec Ref: FR 3.1, AI-008
# =============================================================================


class TestBrandConsistency:
    """Tests for vision-based brand consistency validation.
    Spec Ref: FR 3.1 (Character Consistency Lock), AI-008"""

    @pytest.mark.asyncio
    async def test_consistent_image_passes(self, governor, mock_mcp_client):
        """Matching images should pass brand check. Spec Ref: FR 3.1"""
        result = await governor.validate_brand_consistency(
            generated_image_url="https://cdn.chimera.ai/gen/new_post.png",
            reference_image_id="ref-agent-001",
            agent_id="agent-001",
        )
        assert result["is_consistent"] is True
        assert result["confidence"] >= 0.90

    @pytest.mark.asyncio
    async def test_inconsistent_image_fails(self, governor, mock_mcp_client):
        """Non-matching images should fail brand check. Spec Ref: FR 3.1"""
        mock_mcp_client.call_tool = AsyncMock(return_value={
            "is_consistent": False,
            "confidence": 0.85,
            "reasoning": "Facial features differ significantly from reference.",
        })
        result = await governor.validate_brand_consistency(
            generated_image_url="https://cdn.chimera.ai/gen/wrong_face.png",
            reference_image_id="ref-agent-001",
            agent_id="agent-001",
        )
        assert result["is_consistent"] is False

    @pytest.mark.asyncio
    async def test_vision_api_failure_escalates_to_hitl(self, governor, mock_mcp_client):
        """If vision model fails, escalate to human review. Safety first.
        Spec Ref: FR 3.1"""
        mock_mcp_client.call_tool = AsyncMock(side_effect=Exception("Vision API timeout"))
        with pytest.raises(HumanInterventionRequired):
            await governor.validate_brand_consistency(
                generated_image_url="https://cdn.chimera.ai/gen/timeout.png",
                reference_image_id="ref-agent-001",
                agent_id="agent-001",
            )

    @pytest.mark.asyncio
    async def test_no_mcp_client_escalates_to_hitl(self, mock_redis):
        """Governor without MCP client should escalate brand checks to HITL.
        Spec Ref: FR 3.1"""
        gov = Governor(redis_client=mock_redis, mcp_client=None)
        with pytest.raises(HumanInterventionRequired):
            await gov.validate_brand_consistency(
                generated_image_url="https://cdn.chimera.ai/gen/test.png",
                reference_image_id="ref-001",
                agent_id="agent-001",
            )

    @pytest.mark.asyncio
    async def test_brand_check_uses_mcp_not_direct_api(self, governor, mock_mcp_client):
        """Brand check MUST route through MCPClient, not direct API call.
        Spec Ref: .cursor/rules/project-chimera.mdc Rule 2"""
        await governor.validate_brand_consistency(
            generated_image_url="https://cdn.chimera.ai/gen/test.png",
            reference_image_id="ref-001",
            agent_id="agent-001",
        )
        # Verify MCP client was called (not a direct API)
        mock_mcp_client.call_tool.assert_called_once()
        call_args = mock_mcp_client.call_tool.call_args
        assert call_args.kwargs.get("server_name") or call_args[1].get("server_name") or \
            (len(call_args.args) > 0 and "mcp-server" in str(call_args))


# =============================================================================
# Test Category 6: Master Review Pipeline
# Spec Ref: AI-017
# =============================================================================


class TestMasterReviewPipeline:
    """Tests for the end-to-end review_result pipeline.
    Spec Ref: AI-017 (Judge Review), AI-018 (Confidence Routing)"""

    @pytest.mark.asyncio
    async def test_high_confidence_result_auto_approved(
        self, governor, mock_redis, high_confidence_action
    ):
        """High confidence result flows through pipeline and is auto-approved.
        Spec Ref: AI-017, NFR 1.1"""
        result = await governor.review_result(high_confidence_action)
        assert result["decision"] == "auto_approve"
        assert result["action"] == "committed"

    @pytest.mark.asyncio
    async def test_medium_confidence_result_escalated(
        self, governor, mock_redis, medium_confidence_action
    ):
        """Medium confidence result flows through pipeline and is escalated.
        Spec Ref: AI-017, NFR 1.1"""
        with pytest.raises(HumanInterventionRequired):
            await governor.review_result(medium_confidence_action)
        # Verify it was pushed to HITL queue
        mock_redis.xadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_confidence_result_rejected(
        self, governor, mock_redis, low_confidence_action
    ):
        """Low confidence result is rejected for retry.
        Spec Ref: AI-017, NFR 1.1"""
        result = await governor.review_result(low_confidence_action)
        assert result["decision"] == "reject_retry"
        assert result["action"] == "rejected_for_retry"

    @pytest.mark.asyncio
    async def test_occ_conflict_halts_pipeline(self, governor, mock_redis):
        """OCC conflict stops the review pipeline entirely.
        Spec Ref: FR 6.1, AI-019"""
        mock_redis.get = AsyncMock(return_value="99")  # State drifted to version 99
        action = ConfidenceScoredAction(
            task_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            worker_id="worker-stale",
            confidence_score=0.95,
            reasoning_trace="This result is stale due to state drift.",
            artifact_type="text",
            artifact_body="Stale content",
            state_version_at_start=5,  # Worker started at version 5
        )
        with pytest.raises(OCCConflictError):
            await governor.review_result(action)

    @pytest.mark.asyncio
    async def test_sensitive_topic_escalated_despite_high_confidence(
        self, governor, mock_redis, sensitive_topic_action
    ):
        """Sensitive topic forces HITL even with high confidence.
        Spec Ref: NFR 1.2"""
        with pytest.raises(HumanInterventionRequired) as exc_info:
            await governor.review_result(sensitive_topic_action)
        assert "politics" in str(exc_info.value.reason).lower() or \
            mock_redis.xadd.called

    @pytest.mark.asyncio
    async def test_review_record_contains_required_audit_fields(
        self, governor, mock_redis, high_confidence_action
    ):
        """Every review record must contain audit trail fields.
        Spec Ref: AI-017"""
        result = await governor.review_result(high_confidence_action)
        assert "review_id" in result
        assert "result_id" in result
        assert "task_id" in result
        assert "agent_id" in result
        assert "confidence_score" in result
        assert "decision" in result
        assert "reviewed_at" in result


# =============================================================================
# Test Category 7: Pydantic Model Validation
# Spec Ref: specs/technical.md §2.2
# =============================================================================


class TestPydanticModels:
    """Tests for Pydantic model constraints.
    Spec Ref: specs/technical.md §2.2"""

    def test_confidence_score_must_be_in_range(self):
        """confidence_score must be 0.0-1.0. Spec Ref: NFR 1.0"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfidenceScoredAction(
                task_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                worker_id="worker-bad",
                confidence_score=1.5,  # Out of range
                reasoning_trace="This should fail.",
                artifact_type="text",
                artifact_body="test",
                state_version_at_start=0,
            )

    def test_negative_confidence_score_rejected(self):
        """Negative confidence_score must be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfidenceScoredAction(
                task_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                worker_id="worker-neg",
                confidence_score=-0.1,
                reasoning_trace="This should fail.",
                artifact_type="text",
                artifact_body="test",
                state_version_at_start=0,
            )

    def test_reasoning_trace_minimum_length(self):
        """reasoning_trace must be at least 10 characters. Spec Ref: NFR 1.0"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfidenceScoredAction(
                task_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                worker_id="worker-short",
                confidence_score=0.95,
                reasoning_trace="short",  # < 10 chars
                artifact_type="text",
                artifact_body="test",
                state_version_at_start=0,
            )

    def test_transaction_proposal_requires_positive_amount(self):
        """amount_usdc must be > 0. Spec Ref: FR 5.2"""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TransactionProposal(
                agent_id=str(uuid.uuid4()),
                to_address="0x742d35Cc6634C0532925a3b844Bc9e7595f2bD68",
                amount_usdc=-10.0,
                network="base",
                purpose="Negative amount",
                confidence_score=0.95,
                reasoning_trace="Negative amount should fail.",
            )
