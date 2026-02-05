# Project Chimera: Agentic Infrastructure

> Spec-Driven Infrastructure for Autonomous Influencer Agents

**Status:** Initialized — Specs pending ratification  
**Architecture:** FastRender Swarm (Planner → Worker → Judge) + MCP + Coinbase AgentKit  
**Context:** Addis Ababa resilience, async-first, Redis-backed durability

---

## Repository Structure

```
.
├── .cursor/rules/                  # Cursor agent governance rules
│   ├── agent.mdc                   # Base agent rules
│   └── project-chimera.mdc         # SDD, MCP enforcement, financial safety
├── .github/workflows/
│   └── main.yml                    # CI/CD pipeline
├── specs/                          # Source of Truth — Functional & Technical Specs
│   ├── _meta.md                    # Vision, constraints, spec index
│   ├── functional.md               # User stories, OpenClaw protocols
│   └── technical.md                # JSON schemas, ERD, Redis config, API contracts
├── src/
│   ├── orchestrator/               # Central Control Plane (MCP Host)
│   │   └── mcp_registry.py         # MCP tool interfaces (Twitter, Coinbase)
│   └── swarm/                      # The FastRender Swarm
│       ├── planner/planner.py      # PlannerService scaffold
│       ├── worker/worker.py        # WorkerService scaffold
│       └── judge/governor.py       # Full Governor with CFO pattern
├── skills/
│   └── README.md                   # 3 skill contracts
├── tests/                          # TDD: Failing tests for API contracts
│   ├── test_governor.py            # 38 tests
│   ├── test_mcp_registry.py        # 32 tests
│   ├── test_schemas.py             # 20 tests
│   └── test_skills_interface.py    # 21 tests
├── infrastructure/                 # Docker, Redis, environment configs
│   ├── .env.example                # Required environment variables
│   └── docker-compose.yml
├── research/                       # Architecture strategy & domain research
├── Dockerfile                      # Multi-stage build (python:3.12-slim + uv)
├── Makefile                        # make setup | make test-swarm | make spec-check
├── pyproject.toml                  # Python project config (uv/hatch)
├── README.md
└── .gitignore
```

## Quick Start

```bash
# 1. Initialize environment
make setup

# 2. Run tests (TDD — expect failures until implementation)
make test-swarm

# 3. Check spec alignment
make spec-check

# 4. Build Docker image
make docker-build
```

## Prime Directive

> **No implementation code without a ratified specification.**

Before writing any `.py` file, verify the corresponding requirement exists in `specs/functional.md` or `specs/technical.md`. See `.cursor/rules/project-chimera.mdc` for full governance rules.

## Key Specifications

- **Functional Spec** (`specs/functional.md`): 19 user stories covering Manager Agents, Autonomous Influencer lifecycle, OpenClaw Identity Verification & Availability Beacon protocols
- **Technical Spec** (`specs/technical.md`): Task/Result JSON schemas, PostgreSQL ERD (8 tables), Weaviate class definitions (3 classes), Redis queue configuration with Addis Ababa resilience patterns

## Architecture References

- SRS: `ProjectChimeraSRSDocumentAutonomousInfluencerNetwork.md`
- Strategy: `research/architecture_strategy.md`
- Challenge: `ProjectChimeraTheAgenticInfrastructureChallenge.md`
