"""
Project Chimera — TDD Tests for MCP Registry & Client

These tests validate the MCP tool interface contracts and routing enforcement.
They SHOULD FAIL for integration scenarios until MCP servers are live.

Spec References:
    - specs/functional.md: AI-010 (MCP-only publishing), AI-012 (AI disclosure)
    - specs/technical.md: §6.4 (MCP Tool Call Interface)
    - SRS: §3.2 (MCP Integration Layer), §4.4 (Action System)
    - .cursor/rules/project-chimera.mdc: Rule 2 (MCP Enforcement)
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.orchestrator.mcp_registry import (
    MCPClient,
    MCPServerConfig,
    MCPServerError,
    MCPTimeoutError,
    MCPToolDefinition,
    MCPToolResult,
    MCPTransport,
    MCP_SERVER_REGISTRY,
    TWITTER_POST_TWEET,
    TWITTER_REPLY_MENTIONS,
    TWITTER_GET_TRENDS,
    COINBASE_SEND_PAYMENT,
    COINBASE_GET_BALANCE,
    COINBASE_DEPLOY_TOKEN,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mcp_client():
    """Create an MCPClient with default registry."""
    return MCPClient()


@pytest.fixture
def initialized_client():
    """Create and initialize an MCPClient (sync fixture, init in test)."""
    client = MCPClient()
    return client


# =============================================================================
# Test Category 1: Registry Completeness
# Spec Ref: SRS §3.2.1
# =============================================================================


class TestRegistryCompleteness:
    """Verify all required MCP servers and tools are registered.
    Spec Ref: SRS §3.2.1 (MCP Topology)"""

    def test_twitter_server_registered(self):
        """mcp-server-twitter must be in the registry. Spec Ref: SRS §3.2.1"""
        assert "mcp-server-twitter" in MCP_SERVER_REGISTRY

    def test_coinbase_server_registered(self):
        """mcp-server-coinbase must be in the registry. Spec Ref: SRS §3.2.1"""
        assert "mcp-server-coinbase" in MCP_SERVER_REGISTRY

    def test_twitter_has_three_tools(self):
        """Twitter server must expose post_tweet, reply_mentions, get_trends.
        Spec Ref: SRS §3.2.1"""
        twitter_config = MCP_SERVER_REGISTRY["mcp-server-twitter"]
        tool_names = [t.name for t in twitter_config.tools]
        assert "post_tweet" in tool_names
        assert "reply_mentions" in tool_names
        assert "get_trends" in tool_names

    def test_coinbase_has_three_tools(self):
        """Coinbase server must expose send_payment, get_balance, deploy_token.
        Spec Ref: SRS §4.5"""
        coinbase_config = MCP_SERVER_REGISTRY["mcp-server-coinbase"]
        tool_names = [t.name for t in coinbase_config.tools]
        assert "send_payment" in tool_names
        assert "get_balance" in tool_names
        assert "deploy_token" in tool_names


# =============================================================================
# Test Category 2: Tool Definition Contracts
# Spec Ref: SRS §6.2 (Schema 2)
# =============================================================================


class TestToolDefinitions:
    """Verify tool definitions match SRS API contracts.
    Spec Ref: SRS §6.2"""

    def test_post_tweet_requires_text_content(self):
        """post_tweet must require text_content. Spec Ref: FR 4.0"""
        required = TWITTER_POST_TWEET.input_schema.get("required", [])
        assert "text_content" in required

    def test_post_tweet_has_disclosure_field(self):
        """post_tweet must include disclosure_level for AI labeling.
        Spec Ref: NFR 2.0, AI-012"""
        props = TWITTER_POST_TWEET.input_schema["properties"]
        assert "disclosure_level" in props
        assert "is_generated" in props

    def test_post_tweet_disclosure_default_is_automated(self):
        """disclosure_level must default to 'automated' for Chimera agents.
        Spec Ref: NFR 2.0"""
        props = TWITTER_POST_TWEET.input_schema["properties"]
        assert props["disclosure_level"]["default"] == "automated"

    def test_post_tweet_is_generated_default_true(self):
        """is_generated must default to True. Spec Ref: NFR 2.0"""
        props = TWITTER_POST_TWEET.input_schema["properties"]
        assert props["is_generated"]["default"] is True

    def test_post_tweet_text_max_length(self):
        """Tweet text must not exceed 280 characters. Platform constraint."""
        props = TWITTER_POST_TWEET.input_schema["properties"]
        assert props["text_content"]["maxLength"] == 280

    def test_reply_mentions_requires_mention_id(self):
        """reply_mentions must require mention_id. Spec Ref: FR 4.1"""
        required = TWITTER_REPLY_MENTIONS.input_schema.get("required", [])
        assert "mention_id" in required
        assert "reply_text" in required

    def test_send_payment_requires_address_and_amount(self):
        """send_payment must require to_address and amount_usdc.
        Spec Ref: FR 5.1"""
        required = COINBASE_SEND_PAYMENT.input_schema.get("required", [])
        assert "to_address" in required
        assert "amount_usdc" in required

    def test_send_payment_validates_address_format(self):
        """to_address must validate EVM address format. Spec Ref: FR 5.0"""
        props = COINBASE_SEND_PAYMENT.input_schema["properties"]
        assert "pattern" in props["to_address"]
        assert props["to_address"]["pattern"] == "^0x[a-fA-F0-9]{40}$"

    def test_send_payment_default_network_is_base(self):
        """Default network for send_payment should be Base. Spec Ref: FR 5.1"""
        props = COINBASE_SEND_PAYMENT.input_schema["properties"]
        assert props["network"]["default"] == "base"

    def test_deploy_token_requires_all_fields(self):
        """deploy_token must require token_name, symbol, supply, purpose.
        Spec Ref: FR 5.1"""
        required = COINBASE_DEPLOY_TOKEN.input_schema.get("required", [])
        assert "token_name" in required
        assert "token_symbol" in required
        assert "initial_supply" in required
        assert "purpose" in required

    def test_deploy_token_network_restricted_to_base(self):
        """Token deployment restricted to Base network for MVP.
        Spec Ref: FR 5.1"""
        props = COINBASE_DEPLOY_TOKEN.input_schema["properties"]
        assert props["network"]["enum"] == ["base"]

    def test_get_balance_requires_agent_id(self):
        """get_balance must require agent_id. Spec Ref: MA-006"""
        required = COINBASE_GET_BALANCE.input_schema.get("required", [])
        assert "agent_id" in required

    def test_get_trends_requires_region(self):
        """get_trends must require region. Spec Ref: FR 2.2"""
        required = TWITTER_GET_TRENDS.input_schema.get("required", [])
        assert "region" in required


# =============================================================================
# Test Category 3: Governance Flags
# Spec Ref: .cursor/rules/project-chimera.mdc Rules 2, 4, 5
# =============================================================================


class TestGovernanceFlags:
    """Verify governance metadata on tool definitions.
    Spec Ref: project-chimera.mdc Rules 2, 4, 5"""

    def test_post_tweet_requires_judge_approval(self):
        """Publishing content must pass through Judge. Spec Ref: AI-017"""
        assert TWITTER_POST_TWEET.requires_judge_approval is True

    def test_reply_mentions_requires_judge_approval(self):
        """Replies must pass through Judge. Spec Ref: AI-017"""
        assert TWITTER_REPLY_MENTIONS.requires_judge_approval is True

    def test_get_trends_does_not_require_judge(self):
        """Read-only trend data does not need Judge approval."""
        assert TWITTER_GET_TRENDS.requires_judge_approval is False

    def test_send_payment_is_financial(self):
        """send_payment must be marked financial for @budget_check.
        Spec Ref: Rule 4"""
        assert COINBASE_SEND_PAYMENT.is_financial is True

    def test_deploy_token_is_financial(self):
        """deploy_token must be marked financial. Spec Ref: Rule 4"""
        assert COINBASE_DEPLOY_TOKEN.is_financial is True

    def test_get_balance_is_not_financial(self):
        """get_balance is read-only, not a financial action."""
        assert COINBASE_GET_BALANCE.is_financial is False

    def test_send_payment_requires_judge_approval(self):
        """Financial transactions must pass through CFO Judge. Spec Ref: FR 5.2"""
        assert COINBASE_SEND_PAYMENT.requires_judge_approval is True


# =============================================================================
# Test Category 4: MCPClient Interface
# Spec Ref: specs/technical.md §6.4
# =============================================================================


class TestMCPClientInterface:
    """Tests for the MCPClient call_tool interface.
    Spec Ref: specs/technical.md §6.4"""

    @pytest.mark.asyncio
    async def test_client_requires_initialization(self, mcp_client):
        """Client must be initialized before tool calls. Spec Ref: §6.4"""
        with pytest.raises(RuntimeError, match="not initialized"):
            await mcp_client.call_tool(
                server_name="mcp-server-twitter",
                tool_name="post_tweet",
                arguments={"text_content": "test"},
            )

    @pytest.mark.asyncio
    async def test_unknown_server_raises_error(self, initialized_client):
        """Unknown server name must raise ValueError. Spec Ref: §6.4"""
        await initialized_client.initialize()
        with pytest.raises(ValueError, match="Unknown MCP server"):
            await initialized_client.call_tool(
                server_name="mcp-server-nonexistent",
                tool_name="some_tool",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_error(self, initialized_client):
        """Unknown tool name on valid server must raise ValueError. Spec Ref: §6.4"""
        await initialized_client.initialize()
        with pytest.raises(ValueError, match="Unknown tool"):
            await initialized_client.call_tool(
                server_name="mcp-server-twitter",
                tool_name="nonexistent_tool",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_successful_tool_call_returns_result(self, initialized_client):
        """Successful call returns MCPToolResult with success=True.
        Spec Ref: §6.4"""
        await initialized_client.initialize()
        result = await initialized_client.call_tool(
            server_name="mcp-server-twitter",
            tool_name="post_tweet",
            arguments={"text_content": "Hello from Chimera!"},
        )
        assert isinstance(result, MCPToolResult)
        assert result.success is True
        assert result.server_name == "mcp-server-twitter"
        assert result.tool_name == "post_tweet"

    def test_get_available_tools_returns_all(self, mcp_client):
        """get_available_tools() returns all tools from all servers. Spec Ref: §6.4"""
        tools = mcp_client.get_available_tools()
        assert len(tools) == 6  # 3 Twitter + 3 Coinbase

    def test_get_available_tools_filtered_by_server(self, mcp_client):
        """get_available_tools(server) returns only that server's tools."""
        twitter_tools = mcp_client.get_available_tools("mcp-server-twitter")
        assert len(twitter_tools) == 3
        assert all(t.server_name == "mcp-server-twitter" for t in twitter_tools)

    def test_get_financial_tools(self, mcp_client):
        """get_financial_tools() returns only tools with is_financial=True.
        Spec Ref: Rule 4"""
        financial = mcp_client.get_financial_tools()
        assert len(financial) == 2  # send_payment + deploy_token
        assert all(t.is_financial for t in financial)


# =============================================================================
# Test Category 5: Transport Configuration
# Spec Ref: SRS §3.2.1
# =============================================================================


class TestTransportConfig:
    """Verify transport configurations match SRS topology.
    Spec Ref: SRS §3.2.1"""

    def test_twitter_uses_sse_transport(self):
        """Twitter server uses SSE (remote). Spec Ref: SRS §3.2.1"""
        config = MCP_SERVER_REGISTRY["mcp-server-twitter"]
        assert config.transport == MCPTransport.SSE

    def test_coinbase_uses_stdio_transport(self):
        """Coinbase server uses Stdio (local process). Spec Ref: SRS §3.2.1"""
        config = MCP_SERVER_REGISTRY["mcp-server-coinbase"]
        assert config.transport == MCPTransport.STDIO

    def test_coinbase_has_command(self):
        """Stdio transport requires a command to spawn the process."""
        config = MCP_SERVER_REGISTRY["mcp-server-coinbase"]
        assert config.command is not None
        assert "coinbase" in config.command.lower()

    def test_twitter_has_endpoint_url(self):
        """SSE transport requires an endpoint URL."""
        config = MCP_SERVER_REGISTRY["mcp-server-twitter"]
        assert config.endpoint_url is not None
