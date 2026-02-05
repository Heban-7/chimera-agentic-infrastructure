# Project Chimera — Agentic Infrastructure

> **Spec-Driven Infrastructure for Autonomous AI Influencer Agents**

---

## What Is This Project?

Project Chimera is the **engineering foundation** for building autonomous AI influencers — digital entities that can research trends, create content, engage with audiences, and manage their own crypto wallets, all without a human writing every tweet.

Think of it like this: instead of building one chatbot, we're building a **factory** that can manufacture and manage _thousands_ of AI influencer agents. Each agent has its own personality, memory, and even a crypto wallet.

This repository is **not** the influencers themselves — it's the **factory floor, safety systems, quality control stations, and assembly line** that produces them.

---

## How Does It Work? (The FastRender Swarm)

The system uses a pattern called the **FastRender Swarm**, inspired by how a real creative agency works. Every task goes through three specialized roles:

### 1. The Planner (The Manager)

When a human says "promote Ethiopian fashion on Twitter," the Planner takes that big goal and breaks it into small, concrete tasks:

```
Campaign Goal: "Promote Ethiopian street fashion globally"
         ↓ (LLM decomposes the goal)
Task 1: Research trending fashion topics in Ethiopia
Task 2: Write a tweet about Addis Ababa street style
Task 3: Generate an image prompt for a fashion post
Task 4: Write replies for potential comments
```

The Planner uses an LLM (AI model) to intelligently decompose goals. If something changes mid-campaign (a news event, a trend shift), the Planner dynamically re-plans.

### 2. The Worker (The Hands)

Workers are stateless agents that grab **one task at a time** and execute it. They use the AI model along with the agent's persona (personality, voice, rules) to generate content. Key properties:

- **Isolated**: Workers don't talk to each other. If one crashes, the others keep going.
- **Scalable**: Need to reply to 50 comments? Spin up 50 Workers in parallel.
- **MCP-routed**: All external actions (tweeting, payments) go through the MCP protocol — no direct API calls.

### 3. The Judge/Governor (The Quality Inspector + CFO)

The Judge reviews every single piece of content before it can be published. It does three checks:

| Check                          | What Happens                                       |
| ------------------------------ | -------------------------------------------------- |
| **Confidence Score > 0.90**    | Auto-approved — published immediately              |
| **Confidence Score 0.70–0.90** | Sent to a human for review (HITL queue)            |
| **Confidence Score < 0.70**    | Rejected — Planner retries with new instructions   |
| **Sensitive Topics Detected**  | Always sent to human, regardless of confidence     |
| **Financial Transaction**      | Extra-strict threshold (0.95) + daily budget check |

The Judge also acts as the **CFO** — any crypto transaction must pass a `@budget_check` decorator that verifies the agent hasn't exceeded its daily spending limit.

---

## The Pipeline in Action

```
Human Operator                  Planner                    Worker                     Judge
      │                            │                          │                         │
      │  "Promote Ethiopian        │                          │                         │
      │   fashion on Twitter"      │                          │                         │
      │ ──────────────────────────>│                          │                         │
      │                            │                          │                         │
      │                    (LLM decomposes goal)              │                         │
      │                            │                          │                         │
      │                            │  Task 1: Research trends │                         │
      │                            │ ────────────────────────>│                         │
      │                            │                          │ (LLM generates content) │
      │                            │                          │                         │
      │                            │                          │  Result + confidence     │
      │                            │                          │ ───────────────────────>│
      │                            │                          │                         │
      │                            │                          │         (confidence 0.92 > 0.90)
      │                            │                          │         ✓ AUTO-APPROVED  │
      │                            │                          │                         │
      │                            │  Task 2: Write tweet     │                         │
      │                            │ ────────────────────────>│                         │
      │                            │                          │ (LLM + persona context) │
      │                            │                          │                         │
      │                            │                          │  Result + confidence     │
      │                            │                          │ ───────────────────────>│
      │                            │                          │                         │
      │  ⏳ "Please review this"   │                          │         (confidence 0.78)
      │ <──────────────────────────────────────────────────────────────  HITL ESCALATION│
```

---

## Agent Personas (SOUL.md)

Every AI influencer is defined by a `SOUL.md` file — think of it as the agent's DNA. It contains:

- **Name & Identity**: Who the agent is
- **Voice Traits**: How they talk (Witty, Empathetic, Gen-Z, etc.)
- **Backstory**: Their narrative history (makes the persona feel real)
- **Directives**: Hard rules they must follow (e.g., "Never discuss politics")
- **Languages**: What languages they can use (English, Amharic, etc.)

Example from our demo agent, **Liya Abebe**:

```
Name: Liya Abebe
Niche: Ethiopian Fashion & Culture
Voice: Witty, Warm, Trendsetting, Gen-Z Savvy
Languages: English, Amharic
Directive: "Never discuss politics"
Directive: "Always disclose AI nature when asked directly"
```

The system prompt is dynamically assembled by combining the persona + retrieved memories + current task context — this is the **Hierarchical Memory Retrieval** pattern.

---

## External Connections (MCP Registry)

The agents interact with the outside world through the **Model Context Protocol (MCP)** — a standardized interface that prevents agents from making raw API calls. Think of it as a controlled gateway:

| MCP Server              | Tools                                         | Purpose                  |
| ----------------------- | --------------------------------------------- | ------------------------ |
| **mcp-server-twitter**  | `post_tweet`, `reply_mentions`, `get_trends`  | Social media interaction |
| **mcp-server-coinbase** | `send_payment`, `get_balance`, `deploy_token` | Crypto wallet management |

**Rule**: No code in `src/` is allowed to call Twitter or Coinbase directly — everything goes through the MCP registry. This makes swapping platforms trivial.

---

## Safety Systems

### Financial Governance (The CFO Pattern)

Every financial transaction must pass through a `@budget_check` decorator:

1. Reads the agent's daily spend from Redis
2. If `current_spend + proposed_amount > daily_limit` → **BLOCKED**
3. If confidence < 0.95 → sent to human for review
4. Only if both pass → transaction executes
5. Spend counter is atomically updated

### Sensitive Topic Detection

Content is automatically scanned for sensitive keywords (politics, health advice, financial advice, legal claims). Any detection forces human review, regardless of confidence score.

### Optimistic Concurrency Control (OCC)

If the campaign state changes while a Worker is executing a task (e.g., the campaign was paused), the Judge detects the stale result via version checking and rejects it.

---

## Repository Structure

```
.
├── .cursor/rules/              # AI coding assistant governance
│   └── project-chimera.mdc    # 8 rules: SDD, MCP enforcement, financial safety
├── .github/workflows/
│   └── main.yml               # CI/CD: lint → test → spec-check → docker
├── specs/                     # Source of Truth (read these first!)
│   ├── _meta.md               # Vision & constraints
│   ├── functional.md          # 19 user stories + OpenClaw protocols
│   └── technical.md           # JSON schemas, database ERD, Redis config
├── src/
│   ├── orchestrator/
│   │   ├── llm_client.py      # OpenRouter LLM integration
│   │   ├── mcp_registry.py    # MCP tool definitions (Twitter, Coinbase)
│   │   ├── persona.py         # SOUL.md parser + context assembly
│   │   └── schemas.py         # Task/Result Pydantic models
│   └── swarm/
│       ├── planner/planner.py # Goal → Task DAG decomposition (LLM)
│       ├── worker/worker.py   # Task execution + content generation (LLM)
│       └── judge/governor.py  # Confidence routing, budget checks, brand vision
├── skills/                    # Agent capability contracts
│   └── README.md              # 3 skill interfaces defined
├── tests/                     # 111 tests (TDD)
│   ├── test_governor.py       # 38 tests — confidence, budget, OCC, brand
│   ├── test_mcp_registry.py   # 32 tests — tool contracts, governance flags
│   ├── test_schemas.py        # 20 tests — Task/Result validation
│   └── test_skills_interface.py # 21 tests — skill I/O contracts
├── examples/
│   └── soul_example.md        # Sample agent persona (Liya Abebe)
├── infrastructure/
│   ├── .env.example           # Required environment variables
│   └── docker-compose.yml     # Redis + PostgreSQL + Weaviate (local dev)
├── research/
│   └── architecture_strategy.md # Architecture rationale & diagrams
├── main.py                    # End-to-end pipeline demo
├── Dockerfile                 # Multi-stage build (Python 3.12 + uv)
├── Makefile                   # make setup | test-swarm | spec-check
└── pyproject.toml             # Python project configuration
```

---

## Quick Start

### 1. Set Up Environment

```bash
# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install pydantic httpx python-dotenv pytest pytest-asyncio
```

### 2. Configure API Key

Create a `.env` file in the project root (it's gitignored):

```env
LLM_API_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your-openrouter-api-key-here
LLM_MODEL=arcee-ai/trinity-large-preview:free
```

### 3. Run the Demo Pipeline

```bash
python main.py
```

This runs the full **Planner → Worker → Judge** pipeline:

1. Loads the Liya Abebe persona from `examples/soul_example.md`
2. Planner decomposes a fashion campaign goal into tasks (via LLM)
3. Worker executes each task (generates content via LLM with persona context)
4. Judge evaluates each result (confidence routing, sensitive topic detection)

### 4. Run the Test Suite

```bash
# Run all 111 tests
python -m pytest tests/ -v

# Or use the Makefile
make test-swarm
```

### 5. Check Spec Alignment

```bash
make spec-check
```

---

## Technology Stack

| Layer         | Technology        | Why                               |
| ------------- | ----------------- | --------------------------------- |
| Language      | Python 3.12       | Async support, LLM ecosystem      |
| LLM           | OpenRouter API    | Model-agnostic, OpenAI-compatible |
| Validation    | Pydantic 2.x      | Schema-first development          |
| HTTP          | httpx             | Async HTTP client                 |
| Vector DB     | Weaviate          | Semantic memory (RAG)             |
| Relational DB | PostgreSQL 16     | Financial ledger, ACID compliance |
| Cache/Queue   | Redis 7           | Task queues, episodic memory      |
| Blockchain    | Coinbase AgentKit | Non-custodial crypto wallets      |
| Container     | Docker            | Reproducible builds               |

---

## Design Principles

1. **Spec-Driven Development**: No code without a specification. Every function traces to a spec ID.
2. **MCP-Only External Access**: All external APIs go through the MCP protocol layer.
3. **Addis Ababa Resilience**: Async-first, generous timeouts, exponential backoff with jitter.
4. **Financial Safety**: Every transaction requires `@budget_check` + Judge approval.
5. **Judge-First Commits**: No content is published without passing the Governor's review.

---

## OpenClaw Integration

The system includes two protocols for agent-to-agent communication on the OpenClaw network:

- **Identity Verification Protocol**: Challenge-response authentication with ed25519 signatures
- **Availability Beacon Protocol**: 30-second heartbeats broadcasting capacity, pricing, and network quality

See `specs/functional.md` §5 for full protocol specifications.

---

## Architecture References

- **SRS**: `ProjectChimeraSRSDocumentAutonomousInfluencerNetwork.md`
- **Strategy**: `research/architecture_strategy.md`
- **Challenge**: `ProjectChimeraTheAgenticInfrastructureChallenge.md`

---

_Built with Spec-Driven Development. No vibe coding._
