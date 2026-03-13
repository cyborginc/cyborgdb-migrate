# Open-Source Release Plan

## Phase 1: Blocking — Must-Have Before Public

### 1.1 LICENSE file
- Add license file to repo root
- Add `license` field to `pyproject.toml`

### 1.2 README.md
- Project description and feature highlights
- Installation: `pip install cyborgdb-migrate` + optional source extras
- Quick start: TUI mode (just run `cyborgdb-migrate`)
- Quick start: headless mode with sample TOML config
- Configuration reference (all TOML fields, env var expansion)
- Supported sources table (Pinecone, Qdrant, Weaviate, ChromaDB, Milvus)
- Checkpoint/resume docs

### 1.3 pyproject.toml metadata
- `authors` / `maintainers`
- `license`
- `classifiers` (Development Status, License, Environment, Topic, Python versions)
- `[project.urls]` — Homepage, Repository, Issues

### 1.4 Fix failing tests
- `test_create_index_ivf` — references non-existent `IndexIVF`; fix or remove
- `test_source_list_shows_6_sources` — expects 6 sources, only 5 exist; update assertion

---

## Phase 2: Critical Code Fixes

### 2.1 `exec()` in summary.py (line 174)
- The "Run" button executes user-editable code with `exec()` and no sandbox
- **Options:**
  - **(a)** Keep as-is with a visible disclaimer (it's a local CLI tool, user is running their own code)
  - **(b)** Remove the Run button entirely, keep only Copy
  - **(c)** Restrict execution to a subprocess with timeout

### 2.2 Null guards on `_client` / `_index`
- `destination.py`: methods like `list_indexes()`, `get_count()`, `fetch_by_ids()` crash if called before `connect()`
- All source connectors have the same pattern
- Add early `raise RuntimeError("Not connected")` checks or use a `@requires_connection` decorator

### 2.3 Replace `assert` with `raise` in models.py
- `ready_for_step()` uses `assert` for runtime validation
- Replace with `if ... is None: raise ValueError(...)`

### 2.4 `BaseException` catch in checkpoint.py
- Line 52: `except BaseException` → `except Exception`

---

## Phase 3: High-Priority Code Quality

### 3.1 Cross-platform clipboard
- `pbcopy` is macOS-only (`key_warning.py:51`, `summary.py:144`)
- **Options:**
  - **(a)** Detect platform: `pbcopy` (macOS), `xclip`/`xsel` (Linux), `clip` (Windows)
  - **(b)** Add `pyperclip` as a dependency
  - **(c)** Use Textual's built-in clipboard API if available

### 3.2 Silent exception swallowing
- `destination.py:90`, `key_warning.py:53`, `summary.py:148` — `except Exception` with no logging
- Add `logger.debug()` or `logger.warning()` to each

### 3.3 Remove or justify `tree-sitter` dependencies
- `tree-sitter` and `tree-sitter-python` are in core deps
- If only used for the TextArea syntax highlighting in summary.py, they should either be documented or moved to optional deps

### 3.4 Magic numbers → named constants
- `engine.py:259` — retry delays `[1, 2, 4]`
- `destination.py:62` — `max(8, dimension // 8)` for IVFPQ
- `milvus.py:82` — type `101` for FLOAT_VECTOR

### 3.5 Unused `namespace` parameter
- `weaviate.py` `extract()` accepts `namespace` but ignores it
- Remove or document why it's there (ABC conformance)

---

## Phase 4: Test Gaps

### 4.1 Fix and expand existing tests
- Fix the 2 failing tests (1.4 above)
- Add tests for `cli.py`: `_decode_key()` (hex, base64, invalid input)
- Add tests for `cli.py`: `main()` entry point (argparse paths)

### 4.2 Add missing unit tests
- `destination.py`: connect failure, null-guard errors
- `engine.py`: verify edge cases, cancel-before-run
- `models.py`: invalid step numbers, boundary conditions

### 4.3 UI tests (stretch)
- Screen rendering tests using Textual's pilot
- Navigation flow: forward/back through all screens
- This is lower priority since UI tests are fragile and the TUI is best validated manually

---

## Phase 5: Project Infrastructure

### 5.1 GitHub Actions CI
- Workflow: lint (ruff) + test matrix (Python 3.10, 3.11, 3.12, 3.13)
- Trigger on push to main + PRs

### 5.2 CONTRIBUTING.md
- Dev setup: `pip install -e ".[dev,all]"`
- Running tests: `pytest`
- Linting: `ruff check src/ tests/`
- Docker Compose for local source DBs

### 5.3 Sample config file
- `example-config.toml` in repo root with comments explaining each field

### 5.4 CHANGELOG.md
- Initial entry for v0.1.0

---

## Phase 6: Polish (Optional)

- [ ] Add `py.typed` marker
- [ ] Pin dependency upper bounds (`textual>=0.86,<1.0`, etc.)
- [ ] Add `.pre-commit-config.yaml`
- [ ] Document exit codes in README
- [ ] Network timeouts on source connector `connect()` calls
- [ ] Standardize string formatting to f-strings
