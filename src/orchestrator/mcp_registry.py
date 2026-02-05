"""
Project Chimera — MCP Tool Interface Registry

This module defines the tool interfaces for all MCP servers used by the
Chimera Agent swarm. It serves as the single integration point for external
services, enforcing Rule 2 of project-chimera.mdc: "ALL external interactions
MUST be routed through the MCPClient interface."

Spec References:
    - specs/functional.md: AI-010 (MCP-only publishing), AI-012 (AI disclosure)
    - specs/technical.md: §6.4 (MCP Tool Call Interface)
    - SRS: §3.2 (MCP Integration Layer), §3.2.1 (Topology), §3.2.2 (Primitives)
    - .cursor/rules/project-chimera.mdc: Rule 2 (MCP Enforcement)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("chimera.orchestrator.mcp_registry")


# =============================================================================
# Core MCP Types — Spec Ref: SRS §3.2.2, specs/technical.md §6.4
# =============================================================================


class MCPTransport(str, Enum):
    """
    MCP transport protocols.
    Spec Ref: SRS §3.2.1 (Stdio for local, SSE for remote)
    """

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


@dataclass
class MCPToolResult:
    """
    Standardized result from an MCP tool invocation.
    Spec Ref: specs/technical.md §6.4
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0
    server_name: str = ""
    tool_name: str = ""


class MCPServerError(Exception):
    """Raised when an MCP server returns an error response."""

    def __init__(self, server_name: str, tool_name: str, message: str):
        self.server_name = server_name
        self.tool_name = tool_name
        super().__init__(
            f"MCP Server Error [{server_name}.{tool_name}]: {message}"
        )


class MCPTimeoutError(Exception):
    """Raised when an MCP tool call exceeds the timeout threshold."""

    def __init__(self, server_name: str, tool_name: str, timeout_ms: int):
        self.server_name = server_name
        self.tool_name = tool_name
        self.timeout_ms = timeout_ms
        super().__init__(
            f"MCP Timeout [{server_name}.{tool_name}]: "
            f"exceeded {timeout_ms}ms"
        )


# =============================================================================
# MCP Tool Definitions — Spec Ref: SRS §6.2 Schema 2
# =============================================================================


class MCPToolDefinition(BaseModel):
    """
    Standard MCP Tool definition following the JSON Schema format
    from SRS §6.2 (Schema 2: The MCP Tool Definition).
    """

    name: str = Field(..., description="Tool name as exposed by the MCP server.")
    description: str = Field(..., description="Human-readable description of the tool.")
    input_schema: dict[str, Any] = Field(
        ..., description="JSON Schema defining the tool's input parameters."
    )
    server_name: str = Field(
        ..., description="The MCP server that hosts this tool."
    )
    requires_judge_approval: bool = Field(
        default=False,
        description="If True, invocations must pass through the Judge before execution.",
    )
    is_financial: bool = Field(
        default=False,
        description="If True, the @budget_check decorator is required. Spec Ref: Rule 4.",
    )


@dataclass
class MCPServerConfig:
    """
    Configuration for connecting to an MCP server.
    Spec Ref: SRS §3.2.1
    """

    name: str
    transport: MCPTransport
    command: str | None = None  # For Stdio transport
    endpoint_url: str | None = None  # For SSE/HTTP transport
    env_vars: dict[str, str] = field(default_factory=dict)
    tools: list[MCPToolDefinition] = field(default_factory=list)


# =============================================================================
# Twitter MCP Server — Tool Interfaces
# Spec Ref: SRS §3.2.1 (mcp-server-twitter), §4.4 (Action System)
# =============================================================================

TWITTER_POST_TWEET = MCPToolDefinition(
    name="post_tweet",
    description=(
        "Publishes a tweet to the connected Twitter/X account. "
        "Automatically applies AI disclosure flags per NFR 2.0. "
        "Spec Ref: FR 4.0, AI-010, AI-012"
    ),
    server_name="mcp-server-twitter",
    requires_judge_approval=True,
    input_schema={
        "type": "object",
        "properties": {
            "text_content": {
                "type": "string",
                "maxLength": 280,
                "description": "The tweet body text.",
            },
            "media_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs of media to attach (images/videos).",
            },
            "reply_to_tweet_id": {
                "type": ["string", "null"],
                "description": "If replying, the ID of the parent tweet.",
            },
            "disclosure_level": {
                "type": "string",
                "enum": ["automated", "assisted", "none"],
                "default": "automated",
                "description": (
                    "AI content disclosure level. Must be 'automated' for "
                    "Chimera agents per NFR 2.0."
                ),
            },
            "is_generated": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Platform-native AI labeling flag. MUST be True for all "
                    "Chimera-generated content. Spec Ref: NFR 2.0"
                ),
            },
        },
        "required": ["text_content"],
    },
)

TWITTER_REPLY_MENTIONS = MCPToolDefinition(
    name="reply_mentions",
    description=(
        "Fetches recent mentions and generates context-aware replies. "
        "Part of the bi-directional interaction loop. "
        "Spec Ref: FR 4.1, AI-011"
    ),
    server_name="mcp-server-twitter",
    requires_judge_approval=True,
    input_schema={
        "type": "object",
        "properties": {
            "mention_id": {
                "type": "string",
                "description": "ID of the mention to reply to.",
            },
            "reply_text": {
                "type": "string",
                "maxLength": 280,
                "description": "The reply content.",
            },
            "disclosure_level": {
                "type": "string",
                "enum": ["automated", "assisted", "none"],
                "default": "automated",
            },
            "is_generated": {
                "type": "boolean",
                "default": True,
            },
        },
        "required": ["mention_id", "reply_text"],
    },
)

TWITTER_GET_TRENDS = MCPToolDefinition(
    name="get_trends",
    description=(
        "Retrieves current trending topics for a specified region. "
        "Used by the Trend Spotter background worker. "
        "Spec Ref: FR 2.2, AI-006"
    ),
    server_name="mcp-server-twitter",
    requires_judge_approval=False,
    input_schema={
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "default": "ethiopia",
                "description": "Geographic region for trend data.",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 20,
                "description": "Number of trends to retrieve.",
            },
            "category": {
                "type": ["string", "null"],
                "description": "Optional category filter (e.g., 'fashion', 'tech', 'crypto').",
            },
        },
        "required": ["region"],
    },
)


# =============================================================================
# Coinbase MCP Server — Tool Interfaces
# Spec Ref: SRS §4.5 (Agentic Commerce), §3.2.1 (mcp-server-coinbase)
# =============================================================================

COINBASE_SEND_PAYMENT = MCPToolDefinition(
    name="send_payment",
    description=(
        "Transfer USDC to an external wallet address on the Base network. "
        "MUST be decorated with @budget_check. "
        "Spec Ref: FR 5.1, FR 5.2, AI-016"
    ),
    server_name="mcp-server-coinbase",
    requires_judge_approval=True,
    is_financial=True,
    input_schema={
        "type": "object",
        "properties": {
            "to_address": {
                "type": "string",
                "pattern": "^0x[a-fA-F0-9]{40}$",
                "description": "Recipient EVM wallet address.",
            },
            "amount_usdc": {
                "type": "number",
                "minimum": 0.01,
                "description": "Amount of USDC to transfer.",
            },
            "network": {
                "type": "string",
                "enum": ["base", "ethereum", "solana"],
                "default": "base",
                "description": "Blockchain network for the transaction.",
            },
            "purpose": {
                "type": "string",
                "description": (
                    "Business justification for the payment. "
                    "Required for audit trail and CFO review."
                ),
            },
            "agent_id": {
                "type": "string",
                "format": "uuid",
                "description": "Chimera Agent initiating the payment.",
            },
        },
        "required": ["to_address", "amount_usdc", "purpose", "agent_id"],
    },
)

COINBASE_GET_BALANCE = MCPToolDefinition(
    name="get_balance",
    description=(
        "Check the financial health of an agent's wallet. "
        "The Planner MUST call this before initiating any cost-incurring workflow. "
        "Spec Ref: FR 5.1, MA-006"
    ),
    server_name="mcp-server-coinbase",
    requires_judge_approval=False,
    is_financial=False,
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "format": "uuid",
                "description": "Chimera Agent whose balance to check.",
            },
            "network": {
                "type": "string",
                "enum": ["base", "ethereum", "solana"],
                "default": "base",
                "description": "Blockchain network to query.",
            },
            "tokens": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["USDC", "ETH"],
                "description": "Token symbols to query balances for.",
            },
        },
        "required": ["agent_id"],
    },
)

COINBASE_DEPLOY_TOKEN = MCPToolDefinition(
    name="deploy_token",
    description=(
        "Deploy an ERC-20 token on the Base network (e.g., fan loyalty token). "
        "HIGH-RISK operation — requires Judge approval AND budget_check. "
        "Spec Ref: FR 5.1"
    ),
    server_name="mcp-server-coinbase",
    requires_judge_approval=True,
    is_financial=True,
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "format": "uuid",
                "description": "Chimera Agent deploying the token.",
            },
            "token_name": {
                "type": "string",
                "maxLength": 64,
                "description": "Display name of the token.",
            },
            "token_symbol": {
                "type": "string",
                "maxLength": 10,
                "description": "Token ticker symbol (e.g., 'CHIM').",
            },
            "initial_supply": {
                "type": "integer",
                "minimum": 1,
                "description": "Initial token supply to mint.",
            },
            "network": {
                "type": "string",
                "enum": ["base"],
                "default": "base",
                "description": "Network for deployment. Base only for MVP.",
            },
            "purpose": {
                "type": "string",
                "description": "Business justification for token deployment.",
            },
        },
        "required": [
            "agent_id",
            "token_name",
            "token_symbol",
            "initial_supply",
            "purpose",
        ],
    },
)


# =============================================================================
# MCP Server Registry — Central Configuration
# =============================================================================


MCP_SERVER_REGISTRY: dict[str, MCPServerConfig] = {
    "mcp-server-twitter": MCPServerConfig(
        name="mcp-server-twitter",
        transport=MCPTransport.SSE,
        endpoint_url="${MCP_TWITTER_ENDPOINT:-http://localhost:3001/sse}",
        env_vars={
            "TWITTER_API_KEY": "${TWITTER_API_KEY}",
            "TWITTER_API_SECRET": "${TWITTER_API_SECRET}",
            "TWITTER_ACCESS_TOKEN": "${TWITTER_ACCESS_TOKEN}",
            "TWITTER_ACCESS_SECRET": "${TWITTER_ACCESS_SECRET}",
        },
        tools=[
            TWITTER_POST_TWEET,
            TWITTER_REPLY_MENTIONS,
            TWITTER_GET_TRENDS,
        ],
    ),
    "mcp-server-coinbase": MCPServerConfig(
        name="mcp-server-coinbase",
        transport=MCPTransport.STDIO,
        command="npx -y @coinbase/mcp-server-coinbase",
        env_vars={
            "CDP_API_KEY_NAME": "${CDP_API_KEY_NAME}",
            "CDP_API_KEY_PRIVATE_KEY": "${CDP_API_KEY_PRIVATE_KEY}",
        },
        tools=[
            COINBASE_SEND_PAYMENT,
            COINBASE_GET_BALANCE,
            COINBASE_DEPLOY_TOKEN,
        ],
    ),
}


# =============================================================================
# MCPClient — The Universal Tool Interface
# Spec Ref: specs/technical.md §6.4, .cursor/rules/project-chimera.mdc Rule 2
# =============================================================================


class MCPClient:
    """
    The central MCP client that routes all external tool invocations
    through the registered MCP servers.

    This is the ONLY authorized interface for external interactions.
    Direct SDK calls are PROHIBITED in src/ business logic.

    Spec Ref:
        - specs/technical.md §6.4 (MCP Tool Call Interface)
        - .cursor/rules/project-chimera.mdc Rule 2 (MCP Enforcement)
        - SRS §3.2 (MCP Integration Layer)

    Usage:
        client = MCPClient()
        await client.initialize()
        result = await client.call_tool(
            server_name="mcp-server-twitter",
            tool_name="post_tweet",
            arguments={"text_content": "Hello world!", "is_generated": True}
        )
    """

    def __init__(
        self,
        registry: dict[str, MCPServerConfig] | None = None,
        timeout_ms: int = 30000,
    ):
        """
        Initialize the MCP Client.

        Args:
            registry: Server configurations. Defaults to MCP_SERVER_REGISTRY.
            timeout_ms: Default timeout for tool calls (30s for Addis latency).
        """
        self.registry = registry or MCP_SERVER_REGISTRY
        self.timeout_ms = timeout_ms
        self._connections: dict[str, Any] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """
        Establish connections to all registered MCP servers.
        Must be called before any tool invocations.

        Spec Ref: SRS §3.2.1 (Topology)
        """
        for server_name, config in self.registry.items():
            try:
                # Connection establishment logic will be implemented
                # against the actual MCP SDK. This scaffold defines
                # the interface contract.
                logger.info(
                    "Connecting to MCP server: %s via %s",
                    server_name,
                    config.transport.value,
                )
                self._connections[server_name] = {
                    "config": config,
                    "status": "connected",
                    "connected_at": time.time(),
                }
            except Exception as e:
                logger.error(
                    "Failed to connect to MCP server %s: %s",
                    server_name,
                    str(e),
                )
                self._connections[server_name] = {
                    "config": config,
                    "status": "failed",
                    "error": str(e),
                }

        self._initialized = True
        logger.info(
            "MCP Client initialized with %d servers",
            len(self._connections),
        )

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> MCPToolResult:
        """
        Execute a tool on the specified MCP server.

        ALL external interactions in Project Chimera MUST go through
        this method. Direct SDK calls are prohibited.

        Spec Ref: specs/technical.md §6.4

        Args:
            server_name: The MCP server to invoke (e.g., "mcp-server-twitter").
            tool_name: The tool to call (e.g., "post_tweet").
            arguments: Tool arguments matching the tool's input_schema.
            timeout_ms: Override timeout (default: self.timeout_ms).

        Returns:
            MCPToolResult with success status, data, and latency.

        Raises:
            MCPServerError: If the server returns an error.
            MCPTimeoutError: If the call exceeds timeout.
            ValueError: If server_name or tool_name is not registered.
        """
        if not self._initialized:
            raise RuntimeError(
                "MCPClient not initialized. Call await client.initialize() first."
            )

        # Validate server exists
        if server_name not in self.registry:
            raise ValueError(
                f"Unknown MCP server: {server_name}. "
                f"Registered: {list(self.registry.keys())}"
            )

        # Validate tool exists on this server
        server_config = self.registry[server_name]
        tool_def = next(
            (t for t in server_config.tools if t.name == tool_name),
            None,
        )
        if tool_def is None:
            available = [t.name for t in server_config.tools]
            raise ValueError(
                f"Unknown tool '{tool_name}' on server '{server_name}'. "
                f"Available: {available}"
            )

        # Check if this tool requires Judge approval
        if tool_def.requires_judge_approval:
            logger.info(
                "Tool %s.%s requires Judge approval before execution",
                server_name,
                tool_name,
            )

        # Check if this is a financial tool
        if tool_def.is_financial:
            logger.info(
                "Tool %s.%s is financial — @budget_check required",
                server_name,
                tool_name,
            )

        effective_timeout = timeout_ms or self.timeout_ms
        start_time = time.monotonic()

        try:
            # =============================================================
            # SCAFFOLD: Actual MCP JSON-RPC call will be implemented here
            # using the `mcp` Python SDK. This defines the interface contract.
            #
            # The implementation will:
            # 1. Serialize arguments to JSON-RPC request
            # 2. Send via the configured transport (Stdio/SSE)
            # 3. Await response with timeout
            # 4. Deserialize and return MCPToolResult
            # =============================================================
            logger.info(
                "Calling MCP tool: %s.%s with args: %s",
                server_name,
                tool_name,
                {k: v for k, v in arguments.items() if k not in ("api_key", "secret")},
            )

            # Placeholder for actual implementation
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            return MCPToolResult(
                success=True,
                data={"status": "scaffold", "tool": tool_name},
                latency_ms=elapsed_ms,
                server_name=server_name,
                tool_name=tool_name,
            )

        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            raise MCPTimeoutError(
                server_name=server_name,
                tool_name=tool_name,
                timeout_ms=effective_timeout,
            )
        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            raise MCPServerError(
                server_name=server_name,
                tool_name=tool_name,
                message=str(e),
            )

    def get_available_tools(
        self, server_name: str | None = None
    ) -> list[MCPToolDefinition]:
        """
        List all available tools, optionally filtered by server.

        Args:
            server_name: Filter to a specific server. None returns all.

        Returns:
            List of MCPToolDefinition objects.
        """
        tools: list[MCPToolDefinition] = []
        for name, config in self.registry.items():
            if server_name is None or name == server_name:
                tools.extend(config.tools)
        return tools

    def get_financial_tools(self) -> list[MCPToolDefinition]:
        """
        List all tools marked as financial (requiring @budget_check).
        Spec Ref: .cursor/rules/project-chimera.mdc Rule 4
        """
        return [
            tool
            for config in self.registry.values()
            for tool in config.tools
            if tool.is_financial
        ]

    async def close(self) -> None:
        """Close all MCP server connections."""
        for server_name in self._connections:
            logger.info("Closing connection to MCP server: %s", server_name)
        self._connections.clear()
        self._initialized = False
