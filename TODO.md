# cyborgdb-migrate — Release TODO

## What's Done

### Core
- [x] Project scaffolding (`pyproject.toml`, `src/` layout, entry point)
- [x] `pip install -e ".[dev,all]"` works; `cyborgdb-migrate --version` prints `0.1.0`
- [x] Data models (`VectorRecord`, `SourceInfo`, `MigrationResult`, `MigrationState`)
- [x] Source connector ABC (`CredentialField` with `visible_when`, `SourceConnector`)
- [x] Checkpoint system (atomic save via tmp+rename, load, delete)
- [x] TOML config loader with `${ENV_VAR}` expansion
- [x] CyborgDB destination handler (connect, create/load index, `upsert_binary`, verify)
- [x] `compute_n_lists()` lookup table from PRD
- [x] Key generation + `chmod 600` save, `FileExistsError` guard

### Migration Engine
- [x] Double-buffered extraction/upsert via `ThreadPoolExecutor(1)`
- [x] Random sample caching (4 per batch, no cap) for post-migration verification
- [x] Count check + spot check (`np.allclose` vectors, metadata equality)
- [x] 3-retry exponential backoff (1s/2s/4s) on upsert failures
- [x] Checkpoint every N batches using cursor from `(batch, cursor)` tuples
- [x] Graceful cancellation via `threading.Event`
- [x] Progress callback for UI

### Source Connectors (all 5)
- [x] Pinecone — `list()` pagination + `fetch(include_values=True)`
- [x] Qdrant — `scroll(offset=next_offset)`
- [x] Weaviate — `collection.iterator(include_vector=True)`
- [x] ChromaDB — `get(offset, limit)`, `visible_when` fields, documents → contents
- [x] Milvus — offset-based query, partition support, VARCHAR content heuristic
- [x] `SOURCE_REGISTRY` in `sources/__init__.py`

### TUI (Textual)
- [x] 6-screen wizard (SourceSelect → SourceInspect → CyborgConnect → DestIndex → Migrate → Summary)
- [x] `StepHeader` widget
- [x] `SourceForm` with dynamic field rendering and `visible_when` reactivity
- [x] `KeyWarningModal` requiring "I understand" input
- [x] Live migration dashboard (ProgressBar, stats labels, RichLog, Cancel)
- [x] Checkpoint resume panel on MigrateScreen
- [x] Summary screen with verification results + Python quickstart snippet
- [x] `theme.css`

### CLI
- [x] `--version`, `--config`, `--resume`, `--batch-size`, `--log-file`, `--quiet`
- [x] Headless mode with `rich.progress` output
- [x] File logging via `setup_logging()`

### Tests (134 passing)
- [x] `test_models.py` — dataclass construction, `ready_for_step()` assertions
- [x] `test_checkpoint.py` — save/load/delete, timestamps, overwrite
- [x] `test_config.py` — env var expansion, TOML parsing, validation, defaults
- [x] `test_destination.py` — connect, index CRUD, upsert, count, fetch, key gen
- [x] `test_engine.py` — happy path, empty source, cancellation, retry, resume, verification, sampling, progress
- [x] `test_app.py` — app mounts Screen 1, 5 sources listed, KeyWarningModal gate
- [x] `test_{pinecone,qdrant,weaviate,chromadb,milvus}.py` — credentials, configure, connect, inspect, extract

---

## Before Release

### Bug Fixes
- [x] **Dimension validation for existing index** — added `get_index_dimension()` to `CyborgDestination`, validation in `dest_index.py:_handle_existing()` and `cli.py:run_headless()`
- [x] **Headless key file handling** — `cli.py` now lets `FileExistsError` propagate instead of silently loading existing key
- [x] **Unused `load_config` import** — removed dead import from `cli.py:main()`

### Test Gaps
- [x] Add Weaviate `connect()` tests (with and without API key)
- [x] Add `asyncio_mode = "auto"` to `[tool.pytest.ini_options]` in `pyproject.toml`
- [x] Add headless `run_headless()` tests (happy path, spot check failure, dimension mismatch, key file exists, unknown source)
- [x] Add `get_index_dimension` tests (normal, missing key, error handling)

### Manual Testing
- [ ] Launch TUI (`cyborgdb-migrate`), verify all 6 screens render correctly
- [ ] Walk through TUI with a real source — connect, pick index, create CyborgDB index, run migration, check summary
- [ ] Test "Back" button navigation on each screen
- [ ] Test KeyWarningModal: confirm "I understand" is case-insensitive, Cancel dismisses, Continue proceeds
- [ ] Test cancel mid-migration: click "Cancel Migration", verify checkpoint saved, re-launch and verify "Resume" panel appears
- [ ] Test headless mode: `cyborgdb-migrate --config sample.toml` against a local CyborgDB + ChromaDB
- [ ] Test `--resume` flag with an existing checkpoint
- [ ] Test `--quiet` suppresses progress output
- [ ] Verify `.key` file permissions are 0600 on Linux/macOS
- [ ] Verify checkpoint file is deleted after successful migration

### Integration Tests (local services required)
- [ ] **ChromaDB → CyborgDB** (easiest to set up locally): populate ChromaDB with ~1,000 vectors, run migration, verify count + spot check
- [ ] **Pinecone → CyborgDB**: use a free-tier Pinecone index with a small dataset
- [ ] **Qdrant → CyborgDB**: local Qdrant via Docker (`docker run -p 6333:6333 qdrant/qdrant`)
- [ ] Test checkpoint resume: kill migration mid-run, restart with `--resume`, verify no data loss or duplication
- [ ] Test large batch: 100k+ vectors to exercise double-buffering throughput and checkpoint cadence

### Documentation
- [ ] Write `README.md` — installation, quick start (TUI + headless), config file reference, supported sources
- [ ] Add a `sample.toml` config file for reference
- [ ] Add `CONTRIBUTING.md` with dev setup instructions (`pip install -e ".[dev,all]"`, `pytest`, connector optional deps)

### Polish
- [ ] Review all error messages seen by users — clear, actionable, no tracebacks
- [ ] Verify TUI looks good at 80-column and 120-column terminal widths
- [ ] Test with Python 3.10, 3.11, 3.12, 3.13 (currently developed on 3.14)
- [ ] Confirm `tomli` backport activates correctly on Python <3.11
- [ ] Pin dependency upper bounds if needed for stability (`textual>=0.86,<1.0` etc.)

---

## Open-Source Release

- [ ] Add `LICENSE` file (choose license)
- [ ] Add `py.typed` marker if shipping type stubs
- [ ] Set up GitHub Actions CI: lint (ruff), test matrix (Python 3.10–3.13), build wheel
- [ ] Publish to PyPI: `python -m build && twine upload dist/*`
- [ ] Create GitHub release with changelog
- [ ] Make repo public
