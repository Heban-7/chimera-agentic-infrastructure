# Project Chimera — Technical Specification

> **Version:** 1.0.0-draft  
> **Status:** PENDING RATIFICATION  
> **Last Updated:** 2026-02-05  
> **Source of Truth:** `ProjectChimeraSRSDocumentAutonomousInfluencerNetwork.md`  
> **Architecture Ref:** `research/architecture_strategy.md`

---

## 1. Overview

This document defines the **technical contracts** for Project Chimera: data schemas, database designs, queue configurations, and API boundaries. Every `src/` module must implement against these definitions. Drift is detected by `make spec-check`.

---

## 2. JSON Schemas — Core Data Objects

### 2.1 Task Object

The Task is the unit of work flowing from Planner → Worker via the Redis `task_queue`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ChimeraTask",
  "type": "object",
  "required": [
    "task_id",
    "task_type",
    "priority",
    "agent_id",
    "context",
    "created_at",
    "status",
    "state_version"
  ],
  "properties": {
    "task_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier (UUID v4) for this task."
    },
    "task_type": {
      "type": "string",
      "enum": [
        "generate_content",
        "reply_comment",
        "execute_transaction",
        "deploy_token",
        "trend_analysis",
        "image_generation",
        "video_generation",
        "memory_update"
      ],
      "description": "The category of work to perform."
    },
    "priority": {
      "type": "string",
      "enum": ["critical", "high", "medium", "low"],
      "description": "Execution priority. Critical tasks bypass normal queue ordering."
    },
    "agent_id": {
      "type": "string",
      "format": "uuid",
      "description": "The Chimera Agent this task belongs to."
    },
    "context": {
      "type": "object",
      "required": ["goal_description"],
      "properties": {
        "goal_description": {
          "type": "string",
          "description": "Natural language description of the task objective."
        },
        "persona_constraints": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Behavioral constraints from SOUL.md directives."
        },
        "required_resources": {
          "type": "array",
          "items": { "type": "string" },
          "description": "MCP Resource URIs needed for this task.",
          "examples": ["mcp://twitter/mentions/123", "mcp://memory/recent"]
        },
        "required_tools": {
          "type": "array",
          "items": { "type": "string" },
          "description": "MCP Tool names needed for execution.",
          "examples": ["post_tweet", "generate_image"]
        },
        "budget_limit_usdc": {
          "type": "number",
          "minimum": 0,
          "description": "Maximum spend allowed for this task (in USDC)."
        },
        "character_reference_id": {
          "type": "string",
          "description": "Visual consistency reference ID for image/video generation tasks."
        }
      }
    },
    "assigned_worker_id": {
      "type": ["string", "null"],
      "description": "Worker instance ID processing this task. Null when pending."
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp of task creation."
    },
    "started_at": {
      "type": ["string", "null"],
      "format": "date-time",
      "description": "ISO 8601 timestamp when worker began processing."
    },
    "status": {
      "type": "string",
      "enum": [
        "pending",
        "in_progress",
        "review",
        "approved",
        "rejected",
        "complete",
        "failed",
        "human_review"
      ],
      "description": "Current lifecycle status of the task."
    },
    "state_version": {
      "type": "integer",
      "minimum": 0,
      "description": "OCC version counter. Incremented on every GlobalState mutation. Used by the Judge to detect stale results."
    },
    "retry_count": {
      "type": "integer",
      "minimum": 0,
      "default": 0,
      "description": "Number of times this task has been retried. Max 3."
    },
    "parent_task_id": {
      "type": ["string", "null"],
      "format": "uuid",
      "description": "If this task was decomposed from a parent, reference the parent here."
    }
  }
}
```

### 2.2 Result Object

The Result is the artifact flowing from Worker → Judge via the Redis `review_queue`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ChimeraResult",
  "type": "object",
  "required": [
    "result_id",
    "task_id",
    "agent_id",
    "worker_id",
    "status",
    "confidence_score",
    "reasoning_trace",
    "artifact",
    "created_at",
    "state_version_at_start"
  ],
  "properties": {
    "result_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for this result."
    },
    "task_id": {
      "type": "string",
      "format": "uuid",
      "description": "Reference to the originating Task."
    },
    "agent_id": {
      "type": "string",
      "format": "uuid",
      "description": "The Chimera Agent this result belongs to."
    },
    "worker_id": {
      "type": "string",
      "description": "Identifier of the Worker instance that produced this result."
    },
    "status": {
      "type": "string",
      "enum": ["success", "partial", "failed"],
      "description": "Worker's self-assessment of task completion."
    },
    "confidence_score": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "LLM-estimated confidence in the quality and safety of this result. Drives HITL routing."
    },
    "reasoning_trace": {
      "type": "string",
      "description": "Chain-of-thought explanation from the Worker. Required for audit trail and HITL review."
    },
    "artifact": {
      "type": "object",
      "description": "The generated output. Structure varies by task_type.",
      "properties": {
        "content_type": {
          "type": "string",
          "enum": ["text", "image_url", "video_url", "transaction", "analysis"],
          "description": "Type of the produced artifact."
        },
        "body": {
          "type": "string",
          "description": "Text content or URL reference to the generated asset."
        },
        "media_urls": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Additional media assets associated with this result."
        },
        "metadata": {
          "type": "object",
          "description": "Task-type-specific metadata (e.g., transaction hash, token ID)."
        }
      },
      "required": ["content_type", "body"]
    },
    "sensitive_topics_detected": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of sensitive topic categories detected (politics, health, finance, legal). Presence forces HITL routing."
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp of result creation."
    },
    "state_version_at_start": {
      "type": "integer",
      "minimum": 0,
      "description": "The GlobalState version when the Worker began. Used by Judge for OCC validation."
    },
    "execution_duration_ms": {
      "type": "integer",
      "description": "Wall-clock time the Worker spent on this task."
    },
    "tools_invoked": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tool_name": { "type": "string" },
          "server_name": { "type": "string" },
          "latency_ms": { "type": "integer" },
          "success": { "type": "boolean" }
        }
      },
      "description": "Audit log of MCP tool invocations during task execution."
    }
  }
}
```

---

## 3. Database Design — PostgreSQL (Structured / Financial)

### 3.1 Entity-Relationship Diagram

```
┌─────────────────────┐       ┌─────────────────────────┐
│     agents          │       │     campaigns            │
├─────────────────────┤       ├─────────────────────────┤
│ PK agent_id    UUID │───┐   │ PK campaign_id     UUID │
│    name        TEXT │   │   │    name             TEXT │
│    persona_hash TEXT│   │   │    goal_description TEXT │
│    soul_md_path TEXT│   │   │    status           TEXT │
│    wallet_addr  TEXT│   │   │    budget_usdc   DECIMAL │
│    status       TEXT│   │   │    created_at  TIMESTAMP │
│    created_at TSTZ  │   │   │    updated_at  TIMESTAMP │
│    updated_at TSTZ  │   │   │ FK operator_id      UUID│
└─────────────────────┘   │   └─────────────────────────┘
                          │
    ┌─────────────────────┼──────────────────────────────┐
    │                     │                              │
    ▼                     ▼                              ▼
┌─────────────────────┐ ┌──────────────────────┐ ┌──────────────────────────┐
│  agent_wallets      │ │  campaign_agents     │ │  financial_ledger        │
├─────────────────────┤ ├──────────────────────┤ ├──────────────────────────┤
│ PK wallet_id   UUID │ │ PK id           UUID │ │ PK ledger_id        UUID │
│ FK agent_id    UUID │ │ FK campaign_id   UUID │ │ FK agent_id          UUID │
│    address     TEXT │ │ FK agent_id      UUID │ │    tx_type           TEXT │
│    network     TEXT │ │    role          TEXT │ │    amount_usdc    DECIMAL │
│    provider    TEXT │ │    assigned_at TSTZ   │ │    direction         TEXT │
│    created_at TSTZ  │ └──────────────────────┘ │    counterparty_addr TEXT │
│    is_active   BOOL │                          │    tx_hash           TEXT │
└─────────────────────┘                          │    network           TEXT │
                                                 │    status            TEXT │
┌─────────────────────┐                          │    confidence_score FLOAT│
│  task_log           │                          │    approved_by       TEXT │
├─────────────────────┤                          │    created_at     TSTZ   │
│ PK log_id      UUID │                          └──────────────────────────┘
│ FK agent_id    UUID │
│ FK campaign_id UUID │  ┌──────────────────────────┐
│    task_type   TEXT │  │  daily_spend_summary     │
│    status      TEXT │  ├──────────────────────────┤
│    confidence  FLOAT│  │ PK id               UUID │
│    duration_ms INT  │  │ FK agent_id          UUID │
│    tools_used JSONB │  │    date              DATE │
│    created_at TSTZ  │  │    total_spend_usdc DECIMAL│
│    completed_at TSTZ│  │    total_revenue_usdc DEC │
└─────────────────────┘  │    tx_count          INT  │
                         │    budget_limit_usdc DEC  │
┌─────────────────────┐  │    limit_exceeded    BOOL │
│  operators          │  └──────────────────────────┘
├─────────────────────┤
│ PK operator_id UUID │  ┌──────────────────────────┐
│    email       TEXT │  │  hitl_review_queue       │
│    name        TEXT │  ├──────────────────────────┤
│    role        TEXT │  │ PK review_id        UUID │
│    created_at TSTZ  │  │ FK result_id         UUID │
└─────────────────────┘  │ FK agent_id          UUID │
                         │    review_type        TEXT │
                         │    content_snapshot  JSONB │
                         │    confidence_score  FLOAT│
                         │    reasoning_trace    TEXT │
                         │    reviewer_id        UUID │
                         │    decision           TEXT │
                         │    reviewer_notes     TEXT │
                         │    created_at      TSTZ   │
                         │    resolved_at     TSTZ   │
                         └──────────────────────────┘
```

### 3.2 Key Constraints

| Table                 | Constraint                                                          | Rationale                                           |
| --------------------- | ------------------------------------------------------------------- | --------------------------------------------------- |
| `financial_ledger`    | `CHECK (direction IN ('debit', 'credit'))`                          | ACID compliance for double-entry accounting.        |
| `financial_ledger`    | `CHECK (amount_usdc >= 0)`                                          | No negative amounts; direction indicates flow.      |
| `agent_wallets`       | `UNIQUE (agent_id, network)`                                        | One active wallet per agent per blockchain network. |
| `daily_spend_summary` | `UNIQUE (agent_id, date)`                                           | One summary row per agent per calendar day.         |
| `hitl_review_queue`   | `CHECK (decision IN ('pending', 'approved', 'edited', 'rejected'))` | Enforces valid HITL outcomes.                       |
| `task_log`            | Index on `(agent_id, created_at DESC)`                              | Optimize recent task lookups per agent.             |

### 3.3 Financial Ledger Integrity

All financial operations use **serializable transaction isolation** (`SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`). The `daily_spend_summary` table is updated atomically with every ledger entry via a PostgreSQL trigger:

```sql
CREATE OR REPLACE FUNCTION update_daily_spend()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO daily_spend_summary (id, agent_id, date, total_spend_usdc, tx_count, budget_limit_usdc)
  VALUES (gen_random_uuid(), NEW.agent_id, CURRENT_DATE, NEW.amount_usdc, 1,
    (SELECT budget_usdc FROM campaigns c
     JOIN campaign_agents ca ON ca.campaign_id = c.campaign_id
     WHERE ca.agent_id = NEW.agent_id LIMIT 1))
  ON CONFLICT (agent_id, date)
  DO UPDATE SET
    total_spend_usdc = daily_spend_summary.total_spend_usdc + NEW.amount_usdc,
    tx_count = daily_spend_summary.tx_count + 1,
    limit_exceeded = (daily_spend_summary.total_spend_usdc + NEW.amount_usdc) > daily_spend_summary.budget_limit_usdc;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_daily_spend
  AFTER INSERT ON financial_ledger
  FOR EACH ROW
  WHEN (NEW.direction = 'debit')
  EXECUTE FUNCTION update_daily_spend();
```

---

## 4. Weaviate — Semantic Memory (Vector Database)

### 4.1 Class Definitions

#### 4.1.1 `AgentMemory`

Stores long-term episodic and semantic memories for RAG retrieval.

```json
{
  "class": "AgentMemory",
  "description": "Long-term semantic memory entries for Chimera Agents. Used in RAG pipeline for context assembly.",
  "vectorizer": "text2vec-openai",
  "moduleConfig": {
    "text2vec-openai": {
      "model": "text-embedding-3-large",
      "dimensions": 3072,
      "type": "text"
    }
  },
  "properties": [
    {
      "name": "agent_id",
      "dataType": ["text"],
      "description": "UUID of the owning Chimera Agent.",
      "moduleConfig": { "text2vec-openai": { "skip": true } },
      "indexFilterable": true
    },
    {
      "name": "memory_type",
      "dataType": ["text"],
      "description": "Category: 'interaction', 'observation', 'reflection', 'skill_learned'.",
      "moduleConfig": { "text2vec-openai": { "skip": true } },
      "indexFilterable": true
    },
    {
      "name": "content",
      "dataType": ["text"],
      "description": "The memory content in natural language. This is the primary field for vectorization."
    },
    {
      "name": "context_tags",
      "dataType": ["text[]"],
      "description": "Taxonomy tags for filtering (e.g., 'fashion', 'ethiopia', 'crypto').",
      "indexFilterable": true
    },
    {
      "name": "emotional_valence",
      "dataType": ["number"],
      "description": "Sentiment score (-1.0 to 1.0) of the memory."
    },
    {
      "name": "importance_score",
      "dataType": ["number"],
      "description": "Relevance weight (0.0 to 1.0). Higher scores are prioritized in RAG retrieval."
    },
    {
      "name": "source_interaction_id",
      "dataType": ["text"],
      "description": "Reference to the originating task or interaction."
    },
    {
      "name": "created_at",
      "dataType": ["date"],
      "description": "When this memory was formed."
    }
  ],
  "invertedIndexConfig": {
    "indexTimestamps": true
  },
  "vectorIndexConfig": {
    "distance": "cosine",
    "ef": 256,
    "efConstruction": 512,
    "maxConnections": 64
  }
}
```

#### 4.1.2 `AgentPersonaSnapshot`

Immutable snapshots of agent personas for version control and consistency validation.

```json
{
  "class": "AgentPersonaSnapshot",
  "description": "Versioned snapshots of SOUL.md persona definitions for auditing and consistency.",
  "vectorizer": "text2vec-openai",
  "moduleConfig": {
    "text2vec-openai": {
      "model": "text-embedding-3-large",
      "dimensions": 3072,
      "type": "text"
    }
  },
  "properties": [
    {
      "name": "agent_id",
      "dataType": ["text"],
      "description": "UUID of the Chimera Agent.",
      "moduleConfig": { "text2vec-openai": { "skip": true } },
      "indexFilterable": true
    },
    {
      "name": "version",
      "dataType": ["int"],
      "description": "Monotonically increasing version counter."
    },
    {
      "name": "backstory",
      "dataType": ["text"],
      "description": "Full narrative backstory from SOUL.md. Primary vectorization target."
    },
    {
      "name": "voice_traits",
      "dataType": ["text[]"],
      "description": "Stylistic traits (e.g., 'Witty', 'Empathetic', 'Gen-Z Slang')."
    },
    {
      "name": "directives",
      "dataType": ["text[]"],
      "description": "Hard behavioral constraints."
    },
    {
      "name": "soul_md_hash",
      "dataType": ["text"],
      "description": "SHA-256 hash of the SOUL.md file at snapshot time.",
      "moduleConfig": { "text2vec-openai": { "skip": true } }
    },
    {
      "name": "created_at",
      "dataType": ["date"],
      "description": "Snapshot creation timestamp."
    }
  ]
}
```

#### 4.1.3 `ContentArtifact`

Multimodal content index for cross-referencing generated assets.

```json
{
  "class": "ContentArtifact",
  "description": "Index of all generated content artifacts (text, image, video) for semantic search and deduplication.",
  "vectorizer": "multi2vec-clip",
  "moduleConfig": {
    "multi2vec-clip": {
      "textFields": ["caption"],
      "imageFields": ["image_url"]
    }
  },
  "properties": [
    {
      "name": "agent_id",
      "dataType": ["text"],
      "indexFilterable": true
    },
    {
      "name": "artifact_type",
      "dataType": ["text"],
      "description": "Type: 'tweet', 'instagram_post', 'video_clip', 'reply'.",
      "indexFilterable": true
    },
    {
      "name": "caption",
      "dataType": ["text"],
      "description": "Text content or caption of the artifact."
    },
    {
      "name": "image_url",
      "dataType": ["text"],
      "description": "URL to the generated image (if applicable)."
    },
    {
      "name": "platform",
      "dataType": ["text"],
      "description": "Target platform: 'twitter', 'instagram', 'threads'.",
      "indexFilterable": true
    },
    {
      "name": "engagement_score",
      "dataType": ["number"],
      "description": "Post-publication engagement metrics (likes + shares + comments normalized)."
    },
    {
      "name": "published_at",
      "dataType": ["date"]
    },
    {
      "name": "task_id",
      "dataType": ["text"],
      "description": "Reference to the originating Task."
    }
  ]
}
```

---

## 5. Redis Configuration — Async Resilience for Addis Ababa

### 5.1 Design Rationale

Addis Ababa's internet infrastructure experiences intermittent connectivity, packet loss, and latency spikes (200ms–2000ms). The Redis layer must be configured for **async resilience**: no operation should block the main event loop, and data must survive transient connection drops.

### 5.2 Queue Definitions

| Queue Name                        | Type                | Purpose                        | Consumer          |
| --------------------------------- | ------------------- | ------------------------------ | ----------------- |
| `chimera:task_queue:{agent_id}`   | Redis Stream        | Tasks from Planner → Worker    | Worker Pool       |
| `chimera:review_queue:{agent_id}` | Redis Stream        | Results from Worker → Judge    | Judge Service     |
| `chimera:hitl_queue`              | Redis Stream        | Escalated results → Human      | Dashboard API     |
| `chimera:policy_broadcast`        | Redis Pub/Sub       | Fleet-wide policy updates      | All Planners      |
| `chimera:beacon:{agent_id}`       | Redis Key (TTL)     | Availability beacon state      | OpenClaw Service  |
| `chimera:daily_spend:{agent_id}`  | Redis Hash          | Real-time spend tracking       | CFO Judge         |
| `chimera:episodic:{agent_id}`     | Redis Sorted Set    | Short-term memory (1h window)  | Context Assembly  |
| `chimera:nonce_cache`             | Redis Set (TTL 60s) | Replay protection for OpenClaw | Identity Verifier |

### 5.3 Stream Configuration (Resilience)

```python
# Redis Stream config for Addis Ababa resilience
REDIS_STREAM_CONFIG = {
    # Consumer group ensures at-least-once delivery
    # If a worker crashes, unclaimed messages are re-delivered
    "consumer_group": "chimera_workers",

    # Block for 5 seconds max when waiting for new messages
    # Short enough to detect connection issues quickly
    "block_ms": 5000,

    # Claim pending messages after 30 seconds of no ACK
    # Accounts for high-latency reconnection scenarios
    "pending_claim_timeout_ms": 30000,

    # Keep last 10,000 messages per stream for replay
    # Allows recovery after extended outages
    "maxlen": 10000,

    # Approximate trimming to avoid blocking during trim
    "approximate_trimming": True,

    # Retry policy for transient connection failures
    "retry_policy": {
        "max_retries": 5,
        "base_delay_ms": 1000,
        "max_delay_ms": 30000,
        "backoff_factor": 2.0,  # Exponential backoff
        "jitter": True  # Random jitter to prevent thundering herd
    }
}
```

### 5.4 Connection Pool Configuration

```python
REDIS_POOL_CONFIG = {
    "host": "${REDIS_HOST:-localhost}",
    "port": 6379,
    "db": 0,
    "password": "${REDIS_PASSWORD}",

    # Connection pool for high concurrency
    "max_connections": 50,

    # Socket timeout: generous for Addis latency
    "socket_timeout": 10.0,        # 10s read timeout
    "socket_connect_timeout": 5.0,  # 5s connect timeout

    # Retry on connection error (transient network blips)
    "retry_on_timeout": True,
    "retry_on_error": [
        "ConnectionError",
        "TimeoutError",
        "BusyLoadingError"
    ],

    # Health check interval: detect dead connections
    "health_check_interval": 15,

    # Decode responses to UTF-8 strings
    "decode_responses": True,

    # SSL for production
    "ssl": "${REDIS_SSL:-false}",
}
```

### 5.5 Daily Spend Tracker (Redis Hash)

```
Key:    chimera:daily_spend:{agent_id}
Type:   Hash
TTL:    Expires at midnight UTC+3 (Addis Ababa timezone)

Fields:
  total_usdc      -> "45.50"     (atomically incremented via HINCRBYFLOAT)
  tx_count        -> "12"        (atomically incremented via HINCRBY)
  limit_usdc      -> "50.00"     (set at start of day from campaign config)
  last_tx_id      -> "uuid-v4"   (reference to last transaction)
  last_updated    -> "ISO-8601"  (timestamp of last update)
```

### 5.6 Episodic Memory (Sorted Set)

```
Key:    chimera:episodic:{agent_id}
Type:   Sorted Set
Score:  Unix timestamp (float)
Member: JSON-serialized memory entry
TTL:    3600 seconds (1 hour sliding window)

Cleanup: ZREMRANGEBYSCORE on every read to prune entries older than 1 hour.
```

---

## 6. API Boundaries — Inter-Service Contracts

### 6.1 Planner → Task Queue

```python
async def enqueue_task(task: ChimeraTask) -> str:
    """
    Push a validated Task to the agent's Redis Stream.

    Returns: The stream message ID.
    Raises: RedisConnectionError (retried automatically via backoff).
    """
```

### 6.2 Worker → Review Queue

```python
async def submit_result(result: ChimeraResult) -> str:
    """
    Push a completed Result to the agent's review stream.

    Returns: The stream message ID.
    Raises: RedisConnectionError (retried automatically via backoff).
    """
```

### 6.3 Judge → Commit / Escalate

```python
async def commit_result(result: ChimeraResult, current_state_version: int) -> bool:
    """
    Attempt to commit an approved result to GlobalState.

    Returns: True if committed, False if OCC conflict detected.
    Raises: HumanInterventionRequired if confidence < threshold.
    """
```

### 6.4 MCP Tool Call Interface

```python
async def call_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any]
) -> MCPToolResult:
    """
    Execute a tool on the specified MCP server.

    All external interactions MUST go through this interface.
    Direct SDK calls are prohibited in src/ code.

    Returns: MCPToolResult with status, data, and latency_ms.
    Raises: MCPServerError, MCPTimeoutError.
    """
```

---

## 7. Environment Configuration

### 7.1 Required Environment Variables

| Variable                  | Required    | Description                                      |
| ------------------------- | ----------- | ------------------------------------------------ |
| `REDIS_HOST`              | Yes         | Redis server hostname                            |
| `REDIS_PASSWORD`          | Yes         | Redis authentication                             |
| `REDIS_SSL`               | No          | Enable SSL (default: false)                      |
| `DATABASE_URL`            | Yes         | PostgreSQL connection string                     |
| `WEAVIATE_URL`            | Yes         | Weaviate cluster endpoint                        |
| `WEAVIATE_API_KEY`        | Yes         | Weaviate authentication                          |
| `GOOGLE_API_KEY`          | Yes         | Gemini 3 API access                              |
| `CDP_API_KEY_NAME`        | Yes         | Coinbase AgentKit key name                       |
| `CDP_API_KEY_PRIVATE_KEY` | Yes         | Coinbase AgentKit private key                    |
| `OPENAI_API_KEY`          | Conditional | Required if using OpenAI embeddings for Weaviate |
| `MAX_DAILY_LIMIT_USDC`    | No          | Default daily spend cap (default: 50.0)          |
| `CONFIDENCE_THRESHOLD`    | No          | Auto-approve threshold (default: 0.90)           |
| `HITL_THRESHOLD`          | No          | Async approval lower bound (default: 0.70)       |

---

## 8. Technology Stack

| Layer           | Technology        | Version | Rationale                                         |
| --------------- | ----------------- | ------- | ------------------------------------------------- |
| Runtime         | Python            | 3.12    | Latest stable; asyncio improvements               |
| Package Manager | uv                | latest  | Fast, reliable Python dependency resolution       |
| Data Validation | Pydantic          | 2.x     | Schema-first development, JSON Schema export      |
| AI Framework    | pydantic-ai       | latest  | Type-safe LLM interactions                        |
| Vector DB       | Weaviate          | 1.28+   | HNSW indexing, multi-modal, production-grade RAG  |
| Relational DB   | PostgreSQL        | 16      | ACID compliance, JSONB, triggers                  |
| Cache / Queue   | Redis             | 7.x     | Streams, pub/sub, sorted sets for episodic memory |
| Blockchain      | Coinbase AgentKit | latest  | Non-custodial wallets, ERC-20, Base network       |
| Container       | Docker            | 24+     | Multi-stage builds, slim images                   |
| Orchestration   | asyncio           | stdlib  | Non-blocking I/O for Addis latency tolerance      |

---

_This specification must be ratified before any implementation code is written. See: `.cursor/rules/project-chimera.mdc` for enforcement._
