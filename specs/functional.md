# Project Chimera — Functional Specification

> **Version:** 1.0.0-draft  
> **Status:** PENDING RATIFICATION  
> **Last Updated:** 2026-02-05  
> **Source of Truth:** `ProjectChimeraSRSDocumentAutonomousInfluencerNetwork.md`  
> **Architecture Ref:** `research/architecture_strategy.md`

---

## 1. Overview

This document defines the **functional requirements** for Project Chimera, the AiQEM Autonomous Influencer Network. It translates the SRS into actionable user stories grouped by domain, and specifies two critical protocols for the OpenClaw agent-to-agent ecosystem: **Identity Verification** and the **Availability Beacon**.

---

## 2. Actors & Stakeholders

| Actor                                     | Role                                                           | Interaction Mode                                                       |
| ----------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Network Operator**                      | Strategic Manager — sets campaign goals, monitors fleet health | Orchestrator Dashboard                                                 |
| **Human Reviewer (HITL)**                 | Moderates escalated content from Judge agents                  | Review Queue UI                                                        |
| **Developer / Architect**                 | Extends MCP servers, refines prompts, maintains infrastructure | CLI, API, Git                                                          |
| **Manager Agent**                         | AI tier-1 agent managing a vertical (e.g., "Fashion Ethiopia") | Receives directives from Orchestrator, delegates to Worker Swarms      |
| **Chimera Agent (Autonomous Influencer)** | Sovereign digital entity with persona, memory, and wallet      | Operates within the Planner→Worker→Judge swarm loop                    |
| **External Agent (OpenClaw Peer)**        | Third-party autonomous agent on the OpenClaw network           | Communicates via Identity Verification & Availability Beacon protocols |

---

## 3. User Stories — Manager Agents

### 3.1 Campaign Lifecycle

| ID         | Story                                                                                                                                                            | Acceptance Criteria                                                                                                                       | SRS Ref                    |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| **MA-001** | As a Manager Agent, I need to receive a high-level campaign goal from the Network Operator so that I can decompose it into executable sub-tasks.                 | The Planner Service reads `campaign_goal` from the Orchestrator API, generates a DAG of tasks, and pushes each to the Redis `task_queue`. | FR 6.0, §3.1.1             |
| **MA-002** | As a Manager Agent, I need to dynamically re-plan when the context changes (trend shift, worker failure, budget exhaustion) so that the campaign stays relevant. | On receiving a `context_change_event`, the Planner prunes stale tasks from the DAG and inserts replacement tasks within 5 seconds.        | §3.1.1 Dynamic Re-planning |
| **MA-003** | As a Manager Agent, I need to spawn Sub-Planners for complex verticals (e.g., social engagement, commerce) so that domain expertise is preserved.                | Sub-Planners operate as independent Planner instances scoped to a vertical, each with their own `task_queue` namespace.                   | §3.1.1 Sub-Planners        |
| **MA-004** | As a Manager Agent, I need to monitor the Worker Pool utilization and auto-scale based on Redis queue depth so that throughput matches demand.                   | When `task_queue` depth exceeds `SCALE_UP_THRESHOLD` (configurable, default 50), the system provisions additional Worker containers.      | NFR 3.0                    |
| **MA-005** | As a Manager Agent, I need to enforce fleet-wide policy updates from a single `AGENTS.md` configuration so that governance changes propagate instantly.          | A policy change in `AGENTS.md` is detected within 60 seconds and applied to all active Planner instances via a Redis pub/sub broadcast.   | §1.2 BoardKit              |

### 3.2 Financial Oversight

| ID         | Story                                                                                                                                             | Acceptance Criteria                                                                                                                                                    | SRS Ref        |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| **MA-006** | As a Manager Agent, I need to check `get_balance` before initiating any cost-incurring workflow so that agents never attempt unfunded operations. | The Planner calls `mcp-server-coinbase.get_balance` before creating tasks of type `execute_transaction` or `generate_hero_content`. Abort if balance < estimated cost. | FR 5.1         |
| **MA-007** | As a Manager Agent, I need a daily P&L summary per Chimera Agent so that the Network Operator can assess financial health.                        | A scheduled job aggregates `daily_spend` and `daily_revenue` from the PostgreSQL ledger and exposes it via the Dashboard API.                                          | FR 5.2, UI 1.0 |

---

## 4. User Stories — Autonomous Influencer Lifecycle

### 4.1 Persona Instantiation

| ID         | Story                                                                                                                                                                               | Acceptance Criteria                                                                                                                                                                                     | SRS Ref |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **AI-001** | As a Chimera Agent, I need to be instantiated from a `SOUL.md` file so that my personality, voice, beliefs, and directives are deterministic and version-controlled.                | The `AgentPersona` Pydantic model parses YAML frontmatter (`name`, `id`, `voice_traits[]`, `directives[]`) and markdown body (`backstory`). Validation fails on missing required fields.                | FR 1.0  |
| **AI-002** | As a Chimera Agent, I need hierarchical memory retrieval (Short-Term → Long-Term → System Prompt) before every reasoning step so that I maintain coherence over weeks of operation. | Context assembly fetches Redis episodic cache (last 1 hour), Weaviate semantic search (top-5 memories), and SOUL.md, then injects them into a structured system prompt. Total assembly latency < 500ms. | FR 1.1  |
| **AI-003** | As a Chimera Agent, I need my persona to evolve by writing successful high-engagement interactions to Weaviate so that I "learn" over time.                                         | The Judge triggers `update_memory` on interactions where engagement_score > `EVOLUTION_THRESHOLD` (0.85). The memory is summarized and stored in the `memories` collection.                             | FR 1.2  |

### 4.2 Perception (Sensing the World)

| ID         | Story                                                                                                                                                                                                                   | Acceptance Criteria                                                                                                                                  | SRS Ref |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **AI-004** | As a Chimera Agent, I need to monitor MCP Resources (`twitter://mentions/recent`, `news://ethiopia/fashion/trends`, `market://crypto/eth/price`) on a configurable polling interval so that I perceive external events. | The Perception Service polls each configured Resource at its interval (default 60s). New content is passed through the Semantic Filter.              | FR 2.0  |
| **AI-005** | As a Chimera Agent, I need a Semantic Filter that scores incoming content for relevance to my active goals so that I don't react to noise.                                                                              | Content below `RELEVANCE_THRESHOLD` (0.75) is discarded. Content above triggers a Task for the Planner. Uses Gemini 3 Flash for lightweight scoring. | FR 2.1  |
| **AI-006** | As a Chimera Agent, I need a Trend Spotter background worker that detects emerging topic clusters over 4-hour windows so that I can create timely content.                                                              | Trend Alerts are generated when ≥ 3 related topics appear within the window. Alerts are injected into the Planner context.                           | FR 2.2  |

### 4.3 Creative Production

| ID         | Story                                                                                                                                                                        | Acceptance Criteria                                                                                                                                        | SRS Ref |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **AI-007** | As a Chimera Agent, I need to generate multimodal content (text, image, video) via specialized MCP Tools so that I can produce platform-native assets.                       | Workers invoke `mcp-server-ideogram` for images, `mcp-server-runway` for video, and the Cognitive Core for text. All outputs are validated by the Judge.   | FR 3.0  |
| **AI-008** | As a Chimera Agent, I need a Character Consistency Lock that injects my `character_reference_id` into every image generation request so that I remain visually recognizable. | All image generation payloads include `character_reference_id` from the agent's persona config. The Judge uses Vision-capable model to verify consistency. | FR 3.1  |
| **AI-009** | As a Chimera Agent, I need a tiered video strategy (Tier 1: Living Portraits for daily; Tier 2: Full Text-to-Video for hero content) so that costs are managed.              | The Planner selects the tier based on `task.priority` and available budget. Tier 1 costs < $0.50, Tier 2 costs < $5.00 per generation.                     | FR 3.2  |

### 4.4 Action (Publishing & Engagement)

| ID         | Story                                                                                                                                                                                                  | Acceptance Criteria                                                                                                                                                                          | SRS Ref         |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| **AI-010** | As a Chimera Agent, I need to publish content exclusively through MCP Tools (`twitter.post_tweet`, `instagram.publish_media`) so that governance and rate-limiting are enforced at the protocol layer. | Zero direct API calls exist in `src/`. All external actions route through `MCPClient.call_tool()`.                                                                                           | FR 4.0          |
| **AI-011** | As a Chimera Agent, I need a full bi-directional interaction loop (Ingest → Plan → Generate → Act → Verify) so that I can autonomously engage with my audience.                                        | A mention triggers a Reply Task; the Worker generates a context-aware reply; the Judge validates safety; the Tool executes `twitter.reply_tweet`. End-to-end < 10 seconds for high-priority. | FR 4.1, NFR 3.1 |
| **AI-012** | As a Chimera Agent, I need to set `is_generated: true` / AI disclosure flags on all published content so that I comply with transparency regulations.                                                  | Every publish tool call includes the `disclosure_level: "automated"` parameter. The MCP server maps this to platform-native flags.                                                           | NFR 2.0         |
| **AI-013** | As a Chimera Agent, I need an Honesty Directive that overrides persona constraints when asked "Are you a robot?" so that I truthfully disclose my AI nature.                                           | The system prompt includes an immutable Honesty Directive. If triggered, the response always contains "I am a virtual persona created by AI." regardless of persona voice.                   | NFR 2.1         |

### 4.5 Agentic Commerce

| ID         | Story                                                                                                                                                                         | Acceptance Criteria                                                                                                                                              | SRS Ref |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **AI-014** | As a Chimera Agent, I need a persistent non-custodial wallet (via Coinbase AgentKit) so that I can transact on-chain.                                                         | Wallet is provisioned at agent creation. Private key stored in secrets manager (never logged). Wallet address persisted in PostgreSQL `agent_wallets` table.     | FR 5.0  |
| **AI-015** | As a Chimera Agent, I need to execute `native_transfer`, `deploy_token`, and `get_balance` actions via AgentKit Action Providers so that I can operate as an economic entity. | Each action is available as a callable MCP Tool. All transactions are logged immutably to the PostgreSQL financial ledger.                                       | FR 5.1  |
| **AI-016** | As a Chimera Agent, I need every transaction to pass through the "CFO" Judge with a `@budget_check` decorator so that I cannot exceed daily spend limits.                     | Transactions where `daily_spend + amount > MAX_DAILY_LIMIT` raise `BudgetExceededError`. The CFO flags the task for human review. Daily limit default: $50 USDC. | FR 5.2  |

### 4.6 Governance & Quality

| ID         | Story                                                                                                                                                                 | Acceptance Criteria                                                                                                                                      | SRS Ref                   |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **AI-017** | As a Chimera Agent, I need every Worker output to be reviewed by a Judge before commitment so that hallucinations and unsafe content are caught.                      | No Worker result is committed to GlobalState without Judge approval. The Judge checks: persona alignment, safety filters, OCC state_version.             | FR 6.0, §3.1.3            |
| **AI-018** | As a Chimera Agent, I need confidence-based routing (Auto-Approve > 0.90, Async Approval 0.70-0.90, Reject < 0.70) so that the human is only involved when necessary. | The Judge reads `confidence_score` from the Worker result metadata and routes accordingly. Sensitive topic filter overrides to HITL regardless of score. | NFR 1.0, NFR 1.1, NFR 1.2 |
| **AI-019** | As a Chimera Agent, I need Optimistic Concurrency Control on GlobalState commits so that stale results from slow Workers don't corrupt the campaign state.            | The Judge checks `state_version` at commit time. If version has drifted, the commit is rejected and the task is re-queued.                               | FR 6.1                    |

---

## 5. OpenClaw Integration Protocols

### 5.1 Identity Verification Protocol

**Purpose:** Enable Chimera Agents to prove their identity to other agents on the OpenClaw network, and to verify the identity of incoming peer agents, preventing impersonation and establishing trust.

#### 5.1.1 Protocol Overview

```
┌──────────────────┐         ┌──────────────────┐
│  Chimera Agent A  │         │  OpenClaw Peer B  │
│  (Prover)         │         │  (Verifier)       │
└────────┬─────────┘         └────────┬─────────┘
         │                             │
         │  1. IDENTITY_CHALLENGE      │
         │ <───────────────────────────│
         │                             │
         │  2. IDENTITY_PROOF          │
         │ ────────────────────────────>
         │    { agent_id, nonce,       │
         │      signed_payload,        │
         │      public_key_ref }       │
         │                             │
         │  3. VERIFY against          │
         │     OpenClaw Registry       │
         │            ┌────────────┐   │
         │            │  Registry  │<──│
         │            └────────────┘   │
         │                             │
         │  4. IDENTITY_CONFIRMED /    │
         │     IDENTITY_REJECTED       │
         │ <───────────────────────────│
```

#### 5.1.2 Data Structures

```json
{
  "protocol": "openclaw.identity.v1",
  "message_type": "IDENTITY_PROOF",
  "payload": {
    "agent_id": "chimera-agent-uuid-v4",
    "agent_class": "autonomous_influencer",
    "capabilities": ["content_generation", "commerce", "social_engagement"],
    "network": "chimera_network",
    "operator": "aiqem.tech",
    "nonce": "random-256bit-hex",
    "timestamp": "2026-02-05T12:00:00Z",
    "public_key_ref": "did:key:z6Mk...",
    "signature": "ed25519-signed-payload-hex"
  }
}
```

#### 5.1.3 Verification Rules

1. **Nonce Freshness:** The `nonce` must not have been seen in the last 60 seconds (replay protection via Redis TTL).
2. **Signature Validity:** The `signature` must be verifiable against the `public_key_ref` registered in the OpenClaw Agent Registry.
3. **Capability Match:** The Verifier checks that the Prover's declared `capabilities` are consistent with the Registry entry.
4. **Operator Attestation:** The `operator` field must match a verified organization in the Registry.

---

### 5.2 Availability Beacon Protocol

**Purpose:** Allow Chimera Agents to broadcast their operational status, current capacity, and service offerings to the OpenClaw network, enabling agent-to-agent discovery and collaboration.

#### 5.2.1 Protocol Overview

```
┌──────────────────┐         ┌──────────────────────┐
│  Chimera Agent    │         │  OpenClaw Discovery   │
│  (Broadcaster)    │         │  Service (Listener)   │
└────────┬─────────┘         └────────┬──────────────┘
         │                             │
         │  AVAILABILITY_BEACON        │
         │  (every 30s heartbeat)      │
         │ ────────────────────────────>
         │                             │
         │  Indexed in Discovery       │
         │  Catalog for peer queries   │
         │                             │
         │  BEACON_ACK                 │
         │ <───────────────────────────│
```

#### 5.2.2 Beacon Payload

```json
{
  "protocol": "openclaw.availability.v1",
  "message_type": "AVAILABILITY_BEACON",
  "payload": {
    "agent_id": "chimera-agent-uuid-v4",
    "status": "active | busy | sleeping | maintenance",
    "capabilities_offered": [
      {
        "skill": "content_generation",
        "modalities": ["text", "image", "video"],
        "languages": ["en", "am"],
        "avg_latency_ms": 3500,
        "current_queue_depth": 12
      },
      {
        "skill": "commerce",
        "supported_tokens": ["USDC", "ETH"],
        "network": "base",
        "daily_budget_remaining_usdc": 35.5
      }
    ],
    "pricing": {
      "content_collab_usdc": 2.0,
      "sponsored_mention_usdc": 5.0
    },
    "network_quality": {
      "region": "addis_ababa",
      "avg_latency_to_api_ms": 450,
      "connectivity_score": 0.72
    },
    "heartbeat_interval_s": 30,
    "timestamp": "2026-02-05T12:00:00Z",
    "signature": "ed25519-signed-payload-hex"
  }
}
```

#### 5.2.3 Beacon Rules

1. **Heartbeat Cadence:** Beacons are emitted every `heartbeat_interval_s` (default 30s). Agents not heard from in 3× the interval are marked `presumed_offline`.
2. **Addis Ababa Resilience:** If the agent detects high latency (`avg_latency_to_api_ms > 1000`), it doubles `heartbeat_interval_s` to 60s and sets `connectivity_score` below 0.50, signaling peers to use async communication channels.
3. **Capability Truthfulness:** The `current_queue_depth` and `daily_budget_remaining_usdc` must reflect real-time state from Redis and the Coinbase wallet respectively. Fabricated availability data triggers trust penalties in the OpenClaw reputation system.
4. **Signed Beacons:** Every beacon is signed with the agent's private key to prevent spoofing. Verification follows the same Identity Verification rules (§5.1.3).

---

## 6. Traceability Matrix

| Functional Spec ID | SRS Requirement | Module                             | Test ID                        |
| ------------------ | --------------- | ---------------------------------- | ------------------------------ |
| MA-001             | FR 6.0          | `src/swarm/planner/`               | `test_planner_task_generation` |
| MA-002             | §3.1.1          | `src/swarm/planner/`               | `test_planner_dynamic_replan`  |
| AI-001             | FR 1.0          | `src/orchestrator/persona.py`      | `test_persona_instantiation`   |
| AI-002             | FR 1.1          | `src/orchestrator/context.py`      | `test_hierarchical_memory`     |
| AI-010             | FR 4.0          | `src/orchestrator/mcp_registry.py` | `test_mcp_routing_enforced`    |
| AI-014             | FR 5.0          | `src/swarm/worker/commerce.py`     | `test_wallet_provisioning`     |
| AI-016             | FR 5.2          | `src/swarm/judge/governor.py`      | `test_budget_check_decorator`  |
| AI-017             | FR 6.0, §3.1.3  | `src/swarm/judge/governor.py`      | `test_judge_approval_flow`     |
| AI-018             | NFR 1.0-1.2     | `src/swarm/judge/governor.py`      | `test_confidence_routing`      |
| AI-019             | FR 6.1          | `src/swarm/judge/governor.py`      | `test_occ_state_version`       |

---

## 7. Open Questions (For Ratification Review)

1. **OpenClaw Registry:** Is the Registry a centralized service or a decentralized on-chain contract? The protocol above assumes a centralized lookup for v1.
2. **Beacon Pricing:** Should agent-to-agent pricing be fixed or auction-based?
3. **Sub-Planner Granularity:** How many verticals warrant independent Sub-Planners at MVP?
4. **Sensitive Topic Taxonomy:** Should the keyword list be externalized to a configurable resource or hardcoded?

---

_This specification must be ratified before any implementation code is written. See: `.cursor/rules/project-chimera.mdc` for enforcement._
