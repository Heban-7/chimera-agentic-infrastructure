# =============================================================================
# Project Chimera — Master Makefile
# Ref: ProjectChimeraTheAgenticInfrastructureChallenge.md (Task 3.2)
# =============================================================================

.PHONY: setup test-swarm spec-check lint clean docker-build docker-test help

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PYTHON := python
UV := uv
PYTEST := $(PYTHON) -m pytest
SRC_DIR := src
SPEC_DIR := specs
TEST_DIR := tests
DOCKER_IMAGE := chimera-agentic-infrastructure

# ---------------------------------------------------------------------------
# help: Display available targets
# ---------------------------------------------------------------------------
help: ## Show this help message
	@echo "Project Chimera — Available Commands"
	@echo "====================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# setup: Initialize uv and install all dependencies
# ---------------------------------------------------------------------------
setup: ## Initialize uv environment and install dependencies
	@echo ">>> Initializing Project Chimera environment..."
	$(UV) venv
	$(UV) pip install -e ".[dev]"
	@echo ">>> Creating __init__.py files for Python packages..."
	@$(PYTHON) -c "import pathlib; [p.mkdir(parents=True, exist_ok=True) or (p / '__init__.py').touch() for p in [pathlib.Path(d) for d in ['src', 'src/orchestrator', 'src/swarm', 'src/swarm/planner', 'src/swarm/worker', 'src/swarm/judge', 'skills', 'tests']]]"
	@echo ">>> Setup complete. Activate with: source .venv/bin/activate (Unix) or .venv\\Scripts\\activate (Windows)"

# ---------------------------------------------------------------------------
# test-swarm: Run pytest on the tests/ directory
# ---------------------------------------------------------------------------
test-swarm: ## Run all tests with pytest (expects failing tests in TDD mode)
	@echo ">>> Running Project Chimera test suite..."
	$(PYTEST) $(TEST_DIR)/ -v --tb=short -x --color=yes
	@echo ">>> Test run complete."

# ---------------------------------------------------------------------------
# spec-check: Cross-reference src/ against specs/ requirements
# ---------------------------------------------------------------------------
spec-check: ## Detect drift between src/ functions and specs/ requirements
	@echo ">>> Running Spec-Drift Detector..."
	@echo ">>> Scanning $(SRC_DIR)/ for requirement traceability..."
	@$(PYTHON) -c "\
import pathlib, re, sys;\
spec_ids = set();\
for sf in pathlib.Path('$(SPEC_DIR)').glob('*.md'):\
    content = sf.read_text(encoding='utf-8');\
    spec_ids.update(re.findall(r'(?:FR|NFR|MA|AI|UI)\s*[\d.]+', content));\
print(f'  Found {len(spec_ids)} spec requirements: {sorted(spec_ids)[:10]}...');\
src_files = list(pathlib.Path('$(SRC_DIR)').rglob('*.py'));\
traced = set();\
untraced = [];\
for pf in src_files:\
    content = pf.read_text(encoding='utf-8');\
    refs = re.findall(r'(?:FR|NFR|MA|AI|UI)\s*[\d.]+', content);\
    traced.update(refs);\
    funcs = re.findall(r'(?:def|class)\s+(\w+)', content);\
    for f in funcs:\
        if not any(r in content.split(f)[0][-500:] for r in ['Ref:', 'SRS:', 'Spec:']):\
            if f not in ['__init__', 'main']:\
                untraced.append(f'{pf}::{f}');\
covered = spec_ids & traced;\
uncovered = spec_ids - traced;\
print(f'  Spec coverage: {len(covered)}/{len(spec_ids)} requirements traced in code');\
if uncovered:\
    print(f'  UNCOVERED specs: {sorted(uncovered)}');\
if untraced:\
    print(f'  WARNING: {len(untraced)} functions without spec references:');\
    for u in untraced[:15]:\
        print(f'    - {u}');\
if uncovered:\
    print(f'  DRIFT DETECTED: {len(uncovered)} specs not yet implemented.');\
    sys.exit(1);\
else:\
    print('  All specs accounted for.');\
"
	@echo ">>> Spec check complete."

# ---------------------------------------------------------------------------
# lint: Run linting checks
# ---------------------------------------------------------------------------
lint: ## Run ruff linter on source code
	$(PYTHON) -m ruff check $(SRC_DIR)/ $(TEST_DIR)/

# ---------------------------------------------------------------------------
# docker-build: Build the Docker image
# ---------------------------------------------------------------------------
docker-build: ## Build the Chimera Docker image
	@echo ">>> Building Docker image: $(DOCKER_IMAGE)..."
	docker build -t $(DOCKER_IMAGE) .

# ---------------------------------------------------------------------------
# docker-test: Run tests inside Docker container
# ---------------------------------------------------------------------------
docker-test: docker-build ## Run test suite inside Docker
	@echo ">>> Running tests in Docker..."
	docker run --rm $(DOCKER_IMAGE) python -m pytest tests/ -v --tb=short

# ---------------------------------------------------------------------------
# clean: Remove build artifacts
# ---------------------------------------------------------------------------
clean: ## Remove __pycache__, .pytest_cache, and build artifacts
	@echo ">>> Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache dist build
	@echo ">>> Clean complete."
