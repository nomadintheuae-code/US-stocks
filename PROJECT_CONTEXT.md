# PROJECT CONTEXT

## 1. Project Identity

- **Project name**: SENTINEL PRO - US Stock Scanner
- **Purpose**: Personal US stock scanner focused on high-probability setups using Relative Strength (RS) ratings and Volatility Contraction Patterns (VCP). Built for daily automated scanning, interactive visualization, and portfolio tracking.
- **Repository**: https://github.com/EMMA019/US-stocks
- **Local path**: ~/Projects/US-stocks/
- **Programming language**: Python 3.10+
- **Framework**: Streamlit (dashboard), yfinance (data), pandas/numpy (analysis)
- **Package manager**: pip (requirements.txt)
- **Config system**: config.yaml (params) + .env (secrets) + Pydantic validation (sentinel/config.py)
- **Runtime**: Python 3.14.6 (CachyOS Linux)

## 2. Environment

- **Operating system**: CachyOS Linux (Arch-based)
- **Desktop**: KDE Plasma 6.7.4
- **Architecture**: 64-bit
- **CPU**: Intel Core i5-5350U (4 logical CPUs, 1.80 GHz)
- **RAM**: 8 GiB (7.7 GiB usable)
- **GPU**: Intel HD Graphics 6000 (Wayland)
- **No CUDA/NVIDIA GPU** - No GPU acceleration available
- **Key constraint**: Limited CPU/RAM - must avoid excessive memory usage, aggressive multiprocessing, loading all data at once

## 3. Project Architecture

### Main Components
```
~/Projects/US-stocks/
├── app.py                 # Streamlit dashboard v1 (FMP API based)
├── app2.py                # Streamlit dashboard v2 (yfinance based, ECR strategy)
├── sentinel.py            # Batch scanner (main entry point)
├── config.py              # Backward-compat CONFIG dict + 315 ticker universe (wrapper)
├── config.yaml            # All tunable parameters (single source of truth)
├── core_fmp.py            # Financial Modeling Prep API client
├── sentinel/
│   ├── __init__.py        # Package exports
│   └── config.py          # Pydantic Config class (config.yaml + .env loader)
├── requirements.txt       # Python dependencies
├── .env.sample            # Environment variables template
├── .env                   # Secrets (NOT committed)
├── AUDIT_REPORT.md        # Comprehensive audit report (generated)
├── engines/
│   ├── data.py            # DataEngine (yfinance + caching), CurrencyEngine
│   ├── analysis.py        # VCPAnalyzer, RSAnalyzer, StrategyValidator
│   ├── fundamental.py     # FundamentalEngine, InsiderEngine
│   ├── news.py            # NewsEngine (Yahoo + Google News RSS)
│   ├── ecr_strategy.py    # ECRStrategyEngine (Energy Compression Rotation)
│   ├── sentinel_efficiency.py # SES (Sentinel Efficiency Score)
│   └── notify.py          # Position sizing + LINE Notify
├── results/               # Daily scan JSON outputs
├── cache_v45/             # yfinance OHLCV pickle cache (12h TTL)
├── cache/                 # FMP API cache (legacy)
└── venv/                  # Virtual environment
```

### Data Flow (sentinel.py - Batch Mode)
```
TICKERS (315) → DataEngine.get_data() → RSAnalyzer.get_raw_score() 
    → RSAnalyzer.assign_percentiles() → VCPAnalyzer.calculate()
    → StrategyValidator.run() → Filters (RS≥70, VCP≥55, PF≥1.1)
    → Position sizing → Sector diversification → News fetch → JSON output
```

### Data Flow (app2.py - Interactive Mode)
```
User input → DataEngine.get_data() → ECRStrategyEngine.analyze_single()
    → VCPAnalyzer + SentinelEfficiencyAnalyzer + RSAnalyzer
    → Phase detection (ACCUMULATION/IGNITION/RELEASE) → UI display
```

### Key Characteristics
- Monolithic procedural with modular engines (not cleanly layered)
- Business logic mixed with data fetching and UI
- Two dashboard versions with different data sources
- Tests now exist (offline pytest suite, 40 tests)
- Configuration centralized in config.yaml + .env (Phase 1 complete)

## 4. Important Files

| File | Purpose | Importance |
|------|---------|------------|
| `sentinel.py` | Main batch scanner entry point | Critical |
| `config.py` | Backward-compat CONFIG dict + ticker universe (wrapper over sentinel.config) | Critical |
| `config.yaml` | All tunable parameters (single source of truth) | Critical |
| `sentinel/config.py` | Pydantic Config class (loads config.yaml + .env, validation) | Critical |
| `.env` | Secrets (FMP_API_KEY etc.) - NOT committed | Critical |
| `engines/analysis.py` | VCP, RS, StrategyValidator implementations | Critical |
| `engines/data.py` | DataEngine (yfinance + pickle cache), CurrencyEngine | Critical |
| `engines/ecr_strategy.py` | ECR Strategy Engine (Energy Compression Rotation) | High |
| `engines/sentinel_efficiency.py` | SES (Sentinel Efficiency Score) | High |
| `engines/fundamental.py` | FundamentalEngine, InsiderEngine | Medium |
| `engines/news.py` | NewsEngine (Yahoo + Google News RSS) | Medium |
| `engines/notify.py` | Position sizing + LINE Notify | Medium |
| `app2.py` | Streamlit dashboard v2 (ECR strategy) | High |
| `app.py` | Streamlit dashboard v1 (FMP based) | Medium |
| `core_fmp.py` | FMP API client (env-only key; FMPError/FMPPlanError; 402 isolated) | High |
| `engines/core_fmp.py` | LEGACY duplicate of core_fmp.py (kept in sync for parity) | Low |
| `requirements.txt` | Python dependencies (pinned) | Medium |
| `requirements-dev.txt` | Dev deps (pytest) | Low |
| `pyproject.toml` | Project metadata + pytest config | Low |
| `tests/` | Offline pytest suite (config, fmp, analysis, imports) | Medium |
| `results/*.json` | Daily scan outputs | Medium |
| `.env.sample` | Environment variables template | Low |

## 5. Current Functionality

### Batch Scanner (sentinel.py) ✅ WORKING
- Scans 310 active US tickers for VCP/RS setups (delisted filtered out)
- Completes in ~170s (uncached) / ~5s (cached)
- Outputs JSON with qualified_full, selected (ACTION), watchlist_wait
- Position sizing based on risk (1.5% account risk, max 40% per position)
- Sector diversification (max 2 per sector for ACTION)
- LINE Notify integration (optional)

### Interactive Dashboard (app2.py) ✅ WORKING
- Multi-language UI (Japanese/English)
- ECR Strategy analysis (VCP + SES + RS = Sentinel Rank)
- Phase detection: ACCUMULATION / IGNITION / RELEASE
- Portfolio tracking with P&L, ATR-based stops/targets
- Real-time price updates via yfinance
- AI analysis via DeepSeek API (optional)

### Dashboard v1 (app.py) ✅ WORKING
- FMP API based market ranking
- Single-stock deep dive with charts, fundamentals, news
- Uses Financial Modeling Prep API

## 6. Data Sources

| Data Type | Source | Caching | Notes |
|-----------|--------|---------|-------|
| OHLCV (Daily) | yfinance | Pickle (12h TTL) | 700 days, auto_adjust=True |
| Fundamentals | yfinance `.info` | JSON (24h) | Analyst targets, short interest, ownership |
| Insider Txns | yfinance `.insider_transactions` | JSON (6h) | Last 15 transactions |
| News | Yahoo Finance + Google News RSS | JSON (1h) | Headlines only; BS4 body fetch optional |
| Currency (USD/JPY) | yfinance "JPY=X" | None (real-time) | Fallback 150.0 |
| FMP API | Financial Modeling Prep | JSON (12h-24h) | Used only in app.py |

**API Keys (via environment variables):**
- FMP_API_KEY: Required for app.py (currently hardcoded in core_fmp.py - SECURITY ISSUE)
- DEEPSEEK_API_KEY: Optional, for AI analysis
- LINE_CHANNEL_ACCESS_TOKEN + LINE_USER_ID: Optional, for notifications

## 7. Configuration

### Configuration Hierarchy
1. **config.yaml** - All tunable parameters (Pydantic-validated, sentinel/config.py)
2. **.env** - Secrets (FMP_API_KEY, DEEPSEEK_API_KEY, LINE tokens) - NOT committed
3. **Env var overrides** - CAPITAL_JPY, MAX_POSITIONS, ACCOUNT_RISK_PCT, MIN_RS_RATING, MIN_VCP_SCORE, MIN_PROFIT_FACTOR, STOP_LOSS_ATR, TARGET_R_MULTIPLE
4. **Defaults in code** - Pydantic model defaults (fallback only)

`config.py` (root) is now a backward-compatible wrapper: `CONFIG` dict + `TICKERS` are
populated from the new sentinel.config system. Engine modules continue to
`from config import CONFIG` unchanged.

### Configurable Parameters (config.yaml)
```yaml
capital:   jpy, max_positions, account_risk_pct, max_same_sector, max_position_pct
scan:      min_rs_rating, min_vcp_score, min_profit_factor
exit:      stop_loss_atr, target_r_multiple
vcp:       tightness_periods, volume_lookback_*, ma_periods, pivot_*, max_*_score
rs:        windows, weights, min_data_days
backtest:  lookback_bars, min_bars_for_entry, pivot_lookback, ma_filter_period
ses:       period, thresholds/scores
ecr:       vcp/ses/rs weights, phase detection thresholds
cache:     expiry hours per type, compression
performance: max_workers, batch_size, request_timeout, rate_limit_delay
data:      default_period, min_bars_required, auto_adjust, repair, universe_file, filter_delisted
notification: line_enabled, line_chunk_size
ui:        default_language, chart_days, news_limit
```

### Ticker Universe
- 315 tickers hardcoded in config.py (_ORIGINAL + _EXPANSION)
- Categories: Semiconductors, AI/Cloud, Space/Defense, Consumer, Healthcare, Fintech, Crypto, ETFs, etc.
- Delisted filter enabled: BITF, CFLT, DVAX, HOLX, MMC excluded at load (310 active)
- Optional external universe file via `data.universe_file`

## 8. Algorithms

### RS Calculation (engines/analysis.py:169-194)
```python
# Weighted momentum across multiple timeframes
r12 = (c[-1] / c[-252] - 1) if len(c) >= 252 else (c[-1] / c[0] - 1)  # 12m
r6  = (c[-1] / c[-126] - 1) if len(c) >= 126 else (c[-1] / c[0] - 1)  # 6m
r3  = (c[-1] / c[-63]  - 1) if len(c) >= 63  else (c[-1] / c[0] - 1)  # 3m
r1  = (c[-1] / c[-21]  - 1) if len(c) >= 21  else (c[-1] / c[0] - 1)  # 1m
raw_rs = (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)

# Percentile ranking within universe (1-99)
assign_percentiles(): sort by raw_rs, assign percentile
```

### VCP Scoring (engines/analysis.py:10-163) - Max 105 points
| Component | Weight | Logic |
|-----------|--------|-------|
| Tightness | 40pt | Price range % over 20/30/40/60d; contraction = 20d < 30d < 40d |
| Volume Dry-up | 30pt | 20d avg vol / 60d avg vol (20d prior); <0.45 = 30pt |
| MA Alignment | 30pt | Price>MA50 (10), MA50>MA150 (10), MA150>MA200 (10) |
| Pivot Bonus | 5pt | Distance to 50d high: 0-4% = 5pt, 4-8% = 3pt |

### StrategyValidator Backtest (engines/analysis.py:200-258)
- Simulates pivot breakout + MA50 filter entries
- ATR-based stops (2.0×), R-multiple targets (2.5×)
- 250-bar lookback, calculates Profit Factor

### ECR Strategy (engines/ecr_strategy.py)
- Combines VCP (Energy) + SES (Quality) + RS (Momentum)
- Sentinel Rank = weighted composite
- Phases: ACCUMULATION (high rank, contracting), IGNITION (rank surge/volume), RELEASE (breakdown)

### SES - Sentinel Efficiency Score (engines/sentinel_efficiency.py)
- Fractal Efficiency (30pt): net change / sum of absolute changes
- True Force Index (30pt): volume-weighted price change ratio
- Volatility Squeeze (20pt): current vs past volatility ratio
- Bar Quality (20pt): close location value + body strength

## 9. Current State

### Completed (as of 2026-08-11)
- ✅ Repository cloned to ~/Projects/US-stocks/
- ✅ Virtual environment created, dependencies installed
- ✅ Both Streamlit apps (app.py, app2.py) launch successfully
- ✅ Batch scanner (sentinel.py) completes full 315-ticker scan
- ✅ Comprehensive audit completed (AUDIT_REPORT.md)
- ✅ Cache directories populated (~315 pickle files)
- ✅ Results directory has historical scan outputs
- ✅ Git status: clean (only untracked cache/results/AUDIT_REPORT.md)
- ✅ **Phase 1 (config externalization)**: config.yaml created
- ✅ **Phase 1 (pydantic)**: sentinel/config.py Config class with validation
- ✅ **Phase 1 (dotenv)**: .env loading via python-dotenv (sentinel/config.py + core_fmp.py)
- ✅ **Phase 1 (SECURITY)**: hardcoded FMP API key removed from core_fmp.py + engines/core_fmp.py → env-only (.env)
- ✅ **Phase 1 (backward compat)**: config.py wraps sentinel.config; engines unchanged
- ✅ **Delisted filter**: BITF, CFLT, DVAX, HOLX, MMC excluded (310 active tickers)
- ✅ **.gitignore**: protects .env, caches, results, __pycache__, venv
- ✅ Full scan verified with new config: 310 tickers, 30 qualified, 15 ACTION (82.9s)
- ✅ **FMP news HTTP 402 isolated** (2026-08-12): FMPError/FMPPlanError in core_fmp.py + engines/core_fmp.py; app.py news tab shows a notice instead of crashing
- ✅ **requirements.txt pinned** to verified installed versions (2026-08-12)
- ✅ **requirements-dev.txt + pyproject.toml** created (2026-08-12)
- ✅ **Test suite added** (2026-08-12): tests/ — 40 tests, all passing offline (config, fmp client w/ mocked network, analysis, imports)
- ✅ **README.md rewritten** (2026-08-12): structure, install, config, usage, tests, limitations, security notes
- ✅ **PHASE 1 COMPLETE (2026-08-12)** — see Section 21 session log
- ✅ **Phase 2.1 (reproducibility harness)**: frozen data snapshot (310/310 pickles, sectors, meta) captured at HEAD b5b0986; frozen scan replays live 2026-08-12 decisions EXACTLY (310/30/15 ACTION, decision fields MATCH); golden artifact tests/golden/baseline_2026-08-12.json (no secrets, schema v1); tests/test_regression.py + scripts/capture_frozen_snapshot.py + tests/regression_harness.py; full suite 49 tests passing (2026-08-12)

### Phase 2.1 Status (2026-08-12)
**✅ COMPLETE — Reproducibility gate before indicator refactors**:
- Frozen snapshot at HEAD `b5b0986`: 310 pickles + sectors + meta → `~/ProjectBackups/US-stocks/frozen_snapshots/2026-08-12_b5b0986/` (outside repo, excluded from backups)
- Replay harness (tests/regression_harness.py): yfinance stubbed, fundamentals/news/insider stubbed empty, temp results dir, pure-Python pickling; `run_frozen_scan()` = deterministic offline 310-ticker scan
- Cross-check: frozen vs live `results/2026-08-12.json` → **DECISION MATCH** (counts, order, per-ticker status/rs/vcp/pf/entry/stop/target/shares/sector all identical; only live fundamental/informational fields like analyst/insider/PE intentionally absent — they never drive decisions)
- Golden baseline recorded; 9 regression tests added (golden replay, bit-level determinism, live-decision match, no-secrets, baseline counts, universe↔config, ranking/ordering invariants)
- Full suite: **49 passed** (~2m37s; heavy tests skip if snapshot absent)
- Pre-Phase 2.1 backup verified: `US-stocks_2026-08-12_02-12_pre-phase2_1.tar.gz`
- Working tree clean; NOT committed (commit pending authorization)

### Phase 1 Status (2026-08-12)
**✅ COMPLETE** — Foundation (config externalization + security + tests):
- Config: config.yaml single source of truth + .env secrets + Pydantic validation
- Security: hardcoded key removed → env-only; key rotated; history rewritten; pushed to fork
- Tests: 40 pytest tests passing (offline, no network)
- Dependencies pinned; README rewritten; docs updated
- Working tree ready to commit (commit pending; NO push without authorization)

### Performance Metrics (measured)
- **Full scan (uncached)**: 170s for 315 tickers (~0.54s/ticker)
- **Full scan (cached)**: ~5s
- **RAM usage**: ~300MB during scan
- **CPU**: Single-threaded, ~50-80% on 1 core
- **Disk cache**: ~15MB (315 × ~50KB pickle files)
- **Network**: 315+ yfinance API calls per scan

## 10. Pending Tasks

### Immediate (Phase 1 - Foundation)
- [x] **CRITICAL**: Remove hardcoded FMP API key from core_fmp.py — DONE (env-only)
- [x] **CRITICAL**: Externalize all configuration to config.yaml + .env — DONE
- [x] Create PROJECT_CONTEXT.md (this file) — DONE
- [x] Create AI_INSTRUCTIONS.md — DONE
- [x] Create initial external backup — DONE
- [x] Set up pytest test structure — DONE (40 tests passing)
- [x] Pin requirements.txt + requirements-dev.txt + pyproject.toml — DONE
- [x] Rewrite README.md — DONE
- [x] Create Phase 1 completion checkpoint backup — DONE

### Immediate (Phase 2.1 - Reproducibility gate) ✅ COMPLETE
- [x] Capture frozen data snapshot at HEAD b5b0986 (310 pickles + sectors + meta) — DONE
- [x] Build deterministic replay harness (tests/regression_harness.py) — DONE
- [x] Verify frozen replay == live 2026-08-12 decisions (DECISION MATCH) — DONE
- [x] Write golden baseline artifact (tests/golden/baseline_2026-08-12.json) — DONE
- [x] Add regression tests (9) + scan determinism — DONE (49/49 passing)
- [ ] Commit Phase 2.1 files (authorization pending; NO push)

### Short-term (Phase 2-3)
- [ ] Refactor RSAnalyzer → RSIndicator (configurable windows/weights)
- [ ] Refactor VCPAnalyzer → VCPIndicator (proper pivot/handle detection)
- [ ] Create MarketDataProvider abstraction (yfinance, FMP providers)
- [ ] Implement CacheManager with compression
- [ ] Build UniverseManager (load, validate, filter delisted)
- [ ] Create Strategy abstract base class

### Medium-term (Phase 4-7)
- [ ] Implement VCPBreakoutStrategy with breakout confirmation
- [ ] Implement MinerviniTrendTemplate (8 criteria)
- [ ] Implement RelativeStrengthRanking (vs SPY/sector)
- [ ] BacktestEngine with walk-forward validation
- [ ] Multi-market support (Crypto, Forex)
- [ ] CSV/Excel export from dashboard

## 11. Current Plan

**Phase 1: Foundation (Week 1-2)** - Configuration externalization + security fix
**Phase 2: Indicators Layer (Week 2-3)** - Refactor indicators with configurable params
**Phase 3: Strategies Layer (Week 3-4)** - Strategy abstraction + VCP/Minervini/ECR
**Phase 4: Filters & Ranking (Week 4-5)** - Liquidity, MarketCap, Sector, Fundamental filters
**Phase 5: Backtesting (Week 5-6)** - Walk-forward, purged k-fold, OOS validation
**Phase 6: Output & Integration (Week 6-7)** - Refactor sentinel.py, app2.py to new pipeline
**Phase 7: Multi-Market Support (Week 7-8)** - Crypto, Forex providers

## 12. Engineering Decisions

| Decision | Reason | Date | Consequences |
|----------|--------|------|--------------|
| Use yfinance as primary data source | Free, no API key required, good coverage | 2026-08-11 | Rate limits, occasional delisted ticker errors |
| Pickle caching for OHLCV | Fast serialization, preserves DataFrame structure | 2026-08-11 | Python-only, not compressed, version-sensitive |
| Percentile RS ranking (cross-sectional) | No benchmark dependency, relative strength | 2026-08-11 | Universe composition affects rankings |
| VCP pivot = 50-day high | Simple, captures recent resistance | 2026-08-11 | Not true VCP pivot (should be contraction high) |
| StrategyValidator backtest on same data | Quick validation | 2026-08-11 | Look-ahead bias risk |
| Two separate dashboards (app.py, app2.py) | Different data sources (FMP vs yfinance) | 2026-08-11 | Code duplication, confusion |
| Hardcoded ticker universe | Curated watchlist | 2026-08-11 | Survivorship bias, manual maintenance |

## 13. Known Problems

| Problem | Impact | Status | Possible Solution |
|---------|--------|--------|-------------------|
| **Hardcoded FMP API key in core_fmp.py:11** | Security - exposed credentials | ✅ FIXED (2026-08-11) | Moved to .env, python-dotenv loads it; key in .env, code env-only. KEY WAS IN GIT HISTORY - ROTATE RECOMMENDED |
| **FMP key exposure in git history** | Revoked credential in public GitHub repo history | 🟡 REMEDIATED LOCALLY (history rewritten, credential purged); force-push to origin PENDING approval | 1) `git push --force origin main` after user approval 2) old objects persist on GitHub until GC |
| **FMP news endpoint HTTP 402** | app.py news tab had no news (current FMP plan lacks news access) | ✅ ISOLATED (2026-08-12) | FMPPlanError raised + user-facing notice in app.py; RSS path (engines/news.py) unaffected. Full news requires FMP plan upgrade or RSS switch |
| **Look-ahead bias in StrategyValidator** | Backtest results inflated | OPEN | Use walk-forward, separate train/test |
| **Survivorship bias in universe** | Overestimates strategy performance | OPEN | Use historical universe snapshots |
| **VCP pivot definition incorrect** | False signals, missed setups | OPEN | Implement proper VCP pivot detection (contraction high) |
| **Delisted tickers in universe** | Noisy logs, wasted API calls | ✅ FIXED (2026-08-11) | Filter delisted tickers at load time (config.py + config.yaml filter_delisted) |
| **Configuration scattered** | Hard to tune, inconsistent defaults | ✅ FIXED (2026-08-11) | Centralized in config.yaml + sentinel/config.py (Pydantic) |
| **No .gitignore / .env protection** | Risk of committing secrets | ✅ FIXED (2026-08-11) | .gitignore created |
| **No tests** | No regression protection | ✅ FIXED (2026-08-12) | pytest suite in tests/ (49 tests, offline; + Phase 2.1 deterministic golden replay) |
| **Strategy output not reproducible** | Refactors could silently change scan decisions | ✅ FIXED (2026-08-12) | Phase 2.1 frozen snapshot + golden artifact + regression tests — every future run must reproduce HEAD b5b0986 decisions |
| **requirements unpinned** | Non-reproducible installs | ✅ FIXED (2026-08-12) | requirements.txt pinned to verified versions |
| **Sector filter after ranking** | Unfair percentiles for filtered sectors | OPEN | Filter universe before RS ranking |
| **No breakout confirmation in VCP** | Detects setup only, not trigger | OPEN | Add volume surge + price close above pivot |
| **Single-threaded scanning** | Slow on 315 tickers (170s) | OPEN | ThreadPoolExecutor for I/O bound calls |

## 14. Testing

- **Test framework**: pytest 9.1.1 (configured via pyproject.toml `[tool.pytest.ini_options]`, `pythonpath = ["."]`)
- **Available tests**: 49 (tests/test_config.py, tests/test_fmp.py, tests/test_analysis.py, tests/test_imports.py, tests/test_regression.py)
- **Last test run**: 2026-08-12 — `python -m pytest` → **49 passed** (incl. Phase 2.1 regression suite)
- **Network**: fully mocked (test_fmp.py stubs requests.get; no live API calls in tests). Phase 2.1 regression replay is fully offline — it reads frozen OHLCV pickles and stubs fundamentals/news/insider (never hits yfinance/FMP).
- **Phase 2.1 regression suite** (tests/test_regression.py): replays the 310-ticker scan against a frozen snapshot (stored OUTSIDE repo under ~/ProjectBackups/US-stocks/frozen_snapshots/). Asserts (a) a fresh run reproduces the golden artifact exactly, (b) two runs are identical (determinism), (c) frozen replay matches the live 2026-08-12 reference on decision fields (310 scanned / 30 qualified / 15 ACTION), (d) golden has no secrets + correct baseline counts. Skips cleanly if the snapshot dir is absent; recreate via `./venv/bin/python scripts/capture_frozen_snapshot.py`.
- **Golden artifact**: tests/golden/baseline_2026-08-12.json (machine-readable commitment of HEAD b5b0986 output).
- **Known failing tests**: NONE
- **Run command**: `pytest` (or `./venv/bin/python -m pytest`)
- **Note**: app.py is imported via py_compile/startup check only (Streamlit bare-mode); app2.py is import-tested

## 15. Performance

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| Full scan (uncached) | 170s | 30-45s | Batch yfinance calls, parallel I/O |
| Full scan (cached) | ~5s | ~2s | Compressed cache, lazy loading |
| RAM usage | ~300MB | ~150MB | Chunk processing, streaming |
| CPU cores used | 1 | 2-3 (configurable) | ThreadPoolExecutor for I/O |
| API calls per scan | 315+ | ~50 | Batch requests, better caching |
| Disk cache | 15MB | 10MB | zstd/lz4 compression |

### Bottlenecks (identified)
1. Sequential yfinance calls (no batching)
2. FundamentalEngine.get() per qualified ticker (30+ calls)
3. NewsEngine.get() per top pick (RSS + HTTP)
4. StrategyValidator 250-iteration loop per ticker
5. No connection pooling for HTTP

## 16. Git State

- **Current branch**: main
- **Latest commit**: 40a2cc8 "phase1: record committed HEAD and backup state in PROJECT_CONTEXT" (Phase 1, 2026-08-12)
- **PUSHED**: ✅ origin/main == 40a2cc8 (2026-08-12, normal fast-forward push 0948a74..40a2cc8 — no force). Verified via ls-remote.
- **Previous HEAD**: 0948a74 "daily scan.yml の削除" (REWRITTEN history - credential purged, PUSHED to fork)
- **History note**: 6 commits rewritten via git-filter-repo (2026-08-12) to remove revoked FMP credential. Commit count preserved (185). Old hashes (3c1e44e, 31044d9, 5f44ff7, a353c1b, ad3821b, d84a03b) replaced by new hashes.
- **Remote**: `origin` = https://github.com/nomadintheuae-code/US-stocks.git (user's FORK; re-pointed 2026-08-12). origin/main == 0948a74 (pushed, verified via ls-remote).
- **Upstream**: parent repo EMMA019/US-stocks — NOT modified, NOT pushed to (user does not own it).
- **Uncommitted changes**: Phase 2.1 files pending commit — tests/regression_harness.py, tests/test_regression.py, tests/golden/baseline_2026-08-12.json (new), scripts/capture_frozen_snapshot.py (new), pyproject.toml (markers) — NOT committed (authorization pending; NO push)
- **Untracked (ignored)**: .env, cache_v45/, cache/, results/, __pycache__/, .pytest_cache/, AUDIT_REPORT.md, ~/ProjectBackups/US-stocks/frozen_snapshots/ (outside repo)

## 17. Backup State

- **Latest backup**: 2026-08-12_00-55 (PHASE 1 FINAL — after push to fork; records pushed HEAD 40a2cc8)
- **Backup file**: US-stocks_2026-08-12_00-55_phase1-final-pushed.tar.gz
- **Backup location**: ~/ProjectBackups/US-stocks/
- **Backup format**: tar.gz
- **Backup verified**: Yes (tar -tzf OK; .env excluded; no venv/caches/results/__pycache__/.pytest_cache; no sk- secret pattern)
- **Previous checkpoint**: US-stocks_2026-08-12_00-47_phase1-completion.tar.gz (pre-commit state, retained)
- **Contents**: Source code, engines, sentinel package, tests, config.yaml, .gitignore, configs, requirements, pyproject, README, PROJECT_CONTEXT.md, AI_INSTRUCTIONS.md
- **Excluded**: .env, venv, __pycache__, .pytest_cache, cache_v45/, cache/, results/*.json, .git, *.log
- **Pre-rewrite HEAD recorded**: 3c1e44ed4f06b48579fa0275c8ecdc6d97b6fc3a (stored in /tmp/opencode/pre_rewrite_head.txt)
- **Retained (NOT deleted per user instruction)**: 22-30 (initial, contains REVOKED credential - see note), 23-23 (Phase 1), 23-30 (security checkpoint), 23-44 (post-rotation), 00-01 (pre-rewrite), 00-30 (final checkpoint), 00-47 (Phase 1 completion), 00-55 (Phase 1 final)
- **Pre-Phase 2.1 checkpoint (2026-08-12_02-12)**: US-stocks_2026-08-12_02-12_pre-phase2_1.tar.gz (verified; created before the reproducibility harness)
- **Separate resource**: frozen_snapshots/ at ~/ProjectBackups/US-stocks/ holds the 310-ticker frozen OHLCV snapshot (~13MB pickles + sectors + meta) — intentionally OUTSIDE the repo and EXCLUDED from tarball backups (regenerated from the project when needed)
- **Next backup**: At Phase 2 milestones

## 18. Next Step

**Phase 1 COMPLETE (2026-08-12). Security incident CLOSED. Phase 1 PUSHED to fork. Phase 2.1 (reproducibility gate) COMPLETE.**
1. ✅ Credential rotated; ✅ new key in `.env` (600, ignored); ✅ history rewritten (credential purged, HEAD `0948a74`); ✅ pushed to fork `nomadintheuae-code/US-stocks` (force-with-lease, verified).
2. ✅ FMP news HTTP 402 isolated (FMPPlanError; app.py graceful notice).
3. ✅ Tests added (40 passing), requirements pinned, README rewritten, docs updated.
4. ✅ Phase 1 committed (`4617c29`, `40a2cc8`) and **PUSHED** to fork (normal fast-forward `0948a74..40a2cc8`, no force; verified origin/main == local HEAD).
5. ✅ Phase 1 final checkpoint backup created (00-55, verified).
6. ✅ **Phase 2.1 reproducibility gate** (2026-08-12): frozen snapshot at HEAD `b5b0986` → `~/ProjectBackups/US-stocks/frozen_snapshots/2026-08-12_b5b0986/` (310/310 pickles + sectors + meta); replay harness reproduces live decisions EXACTLY (310/30/15 ACTION, decision fields MATCH); golden artifact `tests/golden/baseline_2026-08-12.json`; 9 regression tests; full suite **49 passed**; pre-Phase 2.1 backup verified (`02-12_pre-phase2_1.tar.gz`).

**Phase 2 (next, NOT started)**: Refactor RSAnalyzer → RSIndicator, VCPAnalyzer → VCPIndicator, MarketDataProvider abstraction, CacheManager with compression — guarded by the Phase 2.1 regression suite (golden replay + determinism). Working tree has uncommitted Phase 2.1 files (commit pending; NO push without authorization).

## 20. SECURITY INCIDENT — FMP API Key Exposure

**Severity**: CRITICAL (public exposure of a live API credential)

### What happened
The FMP API key was hardcoded in `core_fmp.py` and `engines/core_fmp.py` (duplicate file).
Both files were committed to `main` and pushed to the PUBLIC GitHub repository
`https://github.com/EMMA019/US-stocks`. The key therefore exists in the repository's
git history and is retrievable by anyone with repo access (public repo = anyone).

### Exposure scope (verified 2026-08-11, no key value printed)
The key assignment appears in **6 commits on main** (all reachable from `origin/main`):

| Commit | Root `core_fmp.py` | `engines/core_fmp.py` |
|--------|:---:|:---:|
| `3c1e44e` (HEAD, origin/main) | yes | yes |
| `31044d9` | yes | yes |
| `5f44ff7` | no | yes |
| `a353c1b` | no | yes |
| `ad3821b` | no | yes |
| `d84a03b` | no | yes |

- No dangling/unreachable commits contain the key.
- No other files (configs, results, secrets) contain the key.
- The key is a 32-char alphanumeric token (value deliberately NOT recorded here).

### Already fixed (working tree only)
- ✅ Hardcoded key removed from `core_fmp.py` + `engines/core_fmp.py` → now read from `.env` via `python-dotenv` (empty default; code fails gracefully).
- ✅ `.env` created (untracked, git-ignored via `.gitignore`).
- ✅ `.env.sample` uses placeholder only.
- ✅ Verified: no hardcoded key in working tree; `.env` ignored by git.

### Credential rotation status (2026-08-11 → 2026-08-12)
- ✅ **Old credential: ROTATED/REVOKED** by user in FMP dashboard.
- ✅ **New credential: configured locally** in `.env` (file perms 600, git-ignored).
- ✅ New credential validated against FMP API: `/quote` → HTTP 200; quote, historical, profile, fundamentals, analyst-consensus endpoints all OK.
- ⚠️ New credential limitation: `/news/stock-latest` → **HTTP 402** (Payment Required). The plan for the new key does not include the news endpoint. Only `app.py` news tab is affected (uses `core_fmp.get_news`); `app2.py` news uses Yahoo/Google RSS (unaffected). Options: upgrade FMP plan, or switch `app.py` news to yfinance RSS.
- ✅ **Git history: REWRITTEN (2026-08-12)** — revoked credential purged from all 6 affected commits via `git-filter-repo` (regex replace-text, no literal key used). Commit count preserved (185). Old commit hashes replaced; new HEAD `0948a74`. Verified: no credential pattern and no FMP-key-shaped token remains anywhere in history (one historical `inst...` FMP response field name is the only 32-char token and is NOT a credential).
- ✅ **PUSHED (2026-08-12)** to fork `nomadintheuae-code/US-stocks` via `git push --force-with-lease=refs/heads/main:3c1e44e... origin main` (explicit lease; NO plain --force). Fork main now at `0948a74`. `origin` remote re-pointed to the fork URL (https://github.com/nomadintheuae-code/US-stocks.git) so future pushes go there.
- ℹ️ **Original repo `EMMA019/US-stocks` NOT touched** (user does not own it; no push, no request for access). Upstream repo still shows its original history (revoked credential) — outside our control.
- ⚠️ **GitHub caveat**: the fork was created from upstream BEFORE the clean push, so it briefly contained the old history; after the forced update, old commit objects may persist in the fork until GitHub GC, and old clones/caches retain them. Rotation has already invalidated the credential.

### Remaining
- ⏸️ Optional: upgrade FMP plan or switch app.py news to a working source (news endpoint returns HTTP 402 with current plan).
- ℹ️ Note: original `EMMA019/US-stocks` history still contains the revoked (inert) credential; not in our control to change.

### Backup note
- The emergency/checkpoint backup (23-30), the Phase 1 backup (23-23), and the post-rotation
  checkpoint contain the FIXED `core_fmp.py` (env-only) — verified free of the credential.
- ⚠️ The INITIAL backup `US-stocks_2026-08-11_22-30.tar.gz` contains the PRE-FIX `core_fmp.py`
  with the old key value. It is local-only (not public), preserved intentionally as a recovery
  point. The credential is now REVOKED, so the backup is inert but still contains the value.
  Options: keep (local, low risk), or scrub/re-encrypt. User decision. Backups exclude `.env`,
  so the NEW credential is never in any backup.

### Exact next action
1. ✅ User rotated/revoked the FMP key (DONE).
2. ✅ Local `.env` updated with new key (DONE), perms 600, git-ignored.
3. ✅ Git history rewritten locally — revoked credential purged from all 6 commits (DONE, via git-filter-repo, HEAD `0948a74`, 185 commits preserved).
4. ✅ Cleaned history PUSHED to fork `nomadintheuae-code/US-stocks` (force-with-lease; origin remote re-pointed to fork). Original `EMMA019/US-stocks` untouched.
5. ⏸️ Optional: resolve app.py news endpoint (HTTP 402) via FMP plan upgrade or yfinance RSS fallback.
6. ⏸️ Resume Phase 1 completion (pytest, pyproject.toml, commit working tree → will push to fork).

*Do NOT commit the current Phase 1 working-tree changes until this incident is closed —
committing them would entangle the fix with the unremediated history.*

## 21. Session History

### 2026-08-12 02:20 — PHASE 2.1 REPRODUCIBILITY GATE (test infra; NO strategy code touched)
**Goal**: Build a deterministic regression baseline BEFORE any Phase 2 indicator refactors, so strategy behavior changes are always detectable.
**Work completed**:
- Snapshot: copied 310/310 data pickles + sectors/meta from HEAD `b5b0986` → `~/ProjectBackups/US-stocks/frozen_snapshots/2026-08-12_b5b0986/` (out of repo; excluded from backups via `frozen_snapshots` in handle_pre_phase2_1.sh)
- Harness `tests/regression_harness.py`: `run_frozen_scan()` = offline 310-ticker scan (yfinance stubbed, fundamentals/news/insider stubbed empty, temp results dir, deterministic pure-Python pickling); `normalize_results`, `write_golden`, `decision_all` (decision-field projection), snapshot meta + presence helpers
- Capture script `scripts/capture_frozen_snapshot.py`: writes snapshot + regenerates golden + cross-checks frozen replay vs live `results/2026-08-12.json` → **DECISION MATCH** (310 scanned / 30 qualified / 15 ACTION; counts, order, and per-ticker status/rs/vcp/pf/entry/stop/target/shares/sector identical; live-only fundamental fields like analyst/insider/PE never drive decisions)
- Golden `tests/golden/baseline_2026-08-12.json` (schema v1, baseline_commit b5b0986, no secrets — regex-verified)
- `tests/test_regression.py` (9 tests): golden reproduction, bit-identical determinism across independent runs, live-decision match, no-secrets, baseline counts, universe↔config.TICKERS, selected⊆qualified, (status_rank, score) ordering invariant
- pyproject.toml: registered `regression`/`slow` pytest markers
**Tests**: full suite `python -m pytest` → **49 passed** (~2m37s, includes 4 replay runs); py_compile all modules + imports OK
**Results**: Reproducibility gate in place — any future code change that alters decisions will fail the golden replay/determinism tests
**Problems**: One regression test initially encoded a wrong ordering assumption (sorted by score alone); fixed to sentinel's actual (status_rank, score) key — 49/49 green
**Decisions**: Snapshot stored outside repo (git-ignored tracks via marker file); golden IS tracked (machine-readable, secret-free); comparison uses decision-field projection because live fundamental/informational fields differ by design
**Backup**: pre-Phase 2.1 checkpoint `US-stocks_2026-08-12_02-12_pre-phase2_1.tar.gz` (verified)
**Next step**: STOP — report to user; commit Phase 2.1 files pending authorization (NO push)

### 2026-08-12 — PHASE 1 PUSHED TO FORK (approved)
**Goal**: Push the Phase 1 commits to the user's fork (nomadintheuae-code/US-stocks) after explicit approval
**Work completed**:
- Pre-push verification: git status clean; HEAD 40a2cc8 (on cleaned history 0948a74); origin → fork URL; `.env` NOT tracked (only `.env.sample` tracked; `.env` ignored, NOT in HEAD/index); no credential patterns in tracked files; origin/main == 0948a74 (ancestor of HEAD → fast-forward possible)
- Confirmed remote ahead-by-exactly-2 (4617c29, 40a2cc8); merge-base check → FF_OK_ANCESTOR_CONFIRMED
- Pushed with NORMAL push (no --force, no --force-with-lease): `0948a74..40a2cc8 main -> main`
- Post-push verification: local HEAD == origin/main == ls-remote main == 40a2cc8 (SYNCED_OK); git status clean
- Updated PROJECT_CONTEXT.md (Sections 16-18) with final Phase 1 pushed state; created final checkpoint backup 00-55
**Tests**: pre-push verification suite (status/log/remote/env/creds/ancestor) + post-push sync check
**Results**: Phase 1 live on fork at 40a2cc8; working tree clean; no credentials pushed
**Problems**: None (earlier `git ls-files .env` exit-0 was a pathspec false positive — file is not tracked)
**Decisions**: Normal fast-forward push (remote was ancestor); no history rewrite; EMMA019 upstream untouched; 22-30 backup retained
**Backup**: US-stocks_2026-08-12_00-55_phase1-final-pushed.tar.gz (verified)
**Next step**: STOP (per instruction). Phase 2 starts on user command.

### 2026-08-12 — PHASE 1 COMPLETION (tests, pinning, README, validation)
**Goal**: Finish Phase 1 (Foundation): test suite, dependency pinning, README, full validation, commit prep
**Work completed**:
- Isolated FMP news HTTP 402: added FMPError + FMPPlanError to core_fmp.py + engines/core_fmp.py (raise_on_plan param); app.py shows a graceful caption instead of crashing
- Pinned requirements.txt to verified installed versions; created requirements-dev.txt + pyproject.toml (pytest config, pythonpath=".")
- Added tests/ suite: test_config.py, test_fmp.py (network fully mocked), test_analysis.py (synthetic data), test_imports.py → **40 tests, all passing**
- Rewrote README.md (structure, install, config, usage, tests, HTTP 402 limitation, security notes, fork relationship)
- Full validation: py_compile all modules OK; pytest 40/40; full sentinel.py scan OK (310 scanned, 30 qualified, 15 ACTION, runtime 99.5s); .env still git-ignored (perms 600); no credential literals in tracked source
- Updated PROJECT_CONTEXT.md (Phase 1 COMPLETE, testing section, known problems, session log)
**Tests**: `python -m pytest` → 40 passed; py_compile OK; cached sentinel scan OK
**Results**: Phase 1 complete; scanner/dashboards operational; working tree ready to commit
**Problems**: Scan runtime 99.5s vs 82.9s baseline (network variance); legacy results/*.json remain tracked (gitignored but already in history)
**Decisions**: requirements.txt stays the dependency source of truth (pyproject metadata only); tests fully offline (mocked network)
**Backup**: Phase 1 completion checkpoint (Section 17)
**Next step**: Clean commit `phase1: ...` (no push without authorization); then Phase 2

### 2026-08-12 00:25 — CLEANED HISTORY PUSHED TO FORK
**Goal**: Push the credential-free history to the user's GitHub fork
**Work completed**:
- Verified pre-push state (status, HEAD 0948a74 / 185 commits, .env untracked+ignored, history credential-free, cleaned history intact)
- Created fork `nomadintheuae-code/US-stocks` via `gh repo fork` (fork's main initially copied upstream 3c1e44e)
- Re-pointed `origin` → https://github.com/nomadintheuae-code/US-stocks.git
- Pushed with explicit lease: `git push --force-with-lease=refs/heads/main:3c1e44e... origin main` (NO plain --force) → `3c1e44e...0948a74 main -> main (forced update)` exit 0
- Verified: local origin/main == live fork main == 0948a74 (ls-remote); remote URL = fork; status unchanged; history still credential-free
- Original `EMMA019/US-stocks` NOT modified
**Tests**: post-push ls-remote + masked history scan (clean)
**Results**: Security incident closed; cleaned history live on fork; no credentials pushed
**Problems**: Original EMMA019 repo history still contains the revoked (inert) credential — outside our control (user not owner)
**Decisions**: Push to fork (not EMMA019); explicit lease form (no local tracking ref for plain lease form)
**Backup**: US-stocks_2026-08-12_00-30_final-checkpoint.tar.gz (see Section 17)
**Next step**: Optional news HTTP 402 fix; Phase 1 completion (commit to fork)

### 2026-08-12 00:10 — GIT HISTORY CLEANUP COMPLETED
**Goal**: Purge the revoked FMP credential from git history via safe rewrite
**Work completed**:
- Verified git-filter-repo available (installed via pip into venv)
- Created verified safe backup `US-stocks_2026-08-12_00-01_pre-rewrite.tar.gz` (no .env, no active credential, no revoked-credential pattern; pre-rewrite HEAD recorded)
- Masked scan of all existing backups: 22-30 CONTAINS revoked credential; 23-23, 23-30, 23-44, 00-01 clean
- Identified affected commits (6) + files (core_fmp.py, engines/core_fmp.py) — no secret printed
- Rewrote history with `git-filter-repo --replace-text` using a REGEX (never the literal credential): pattern `os.environ.get("FMP_API_KEY", "<20+ alnum>")` → `os.environ.get("FMP_API_KEY", "")`
- Re-added origin remote (filter-repo removes it); restored working-tree files from pre-rewrite backup; git status identical to pre-rewrite
- Verified: credential pattern absent from ALL history; only historical 32-char token is an `inst...` FMP field name (not a credential); commit count preserved (185); new HEAD 0948a74
- Working tree verified: py_compile OK, all imports OK, full sentinel scan OK (310 tickers, 30 qualified, 15 ACTION, 82.9s); .env still git-ignored (perms 600)
- NO push performed
**Tests**: py_compile + import checks + full sentinel.py scan (cached) — all pass
**Results**: History clean of revoked credential; app fully functional; only remaining item = force-push (needs approval)
**Problems**: None (push deliberately withheld); GitHub old objects persist until GC after eventual push
**Decisions**: Used regex replace (no literal key in any command); restored working tree from backup rather than stash (avoids filter-repo gc deleting stash objects)
**Backup**: US-stocks_2026-08-12_00-01_pre-rewrite.tar.gz (verified)
**Next step**: Await approval for `git push --force origin main`; then news HTTP 402 fix + Phase 1 completion

### 2026-08-11 23:50 — KEY ROTATION COMPLETED
**Goal**: Configure the new (rotated) FMP credential locally and verify the app without exposing the credential
**Work completed**:
- Old credential confirmed REVOKED by user
- New credential installed into `.env` (updated in place from secure temp file; temp file deleted immediately after)
- `.env` perms tightened to 600; confirmed git-ignored (`.gitignore:2`) and absent from git status
- Verified: 0 hardcoded credentials in any tracked source; new value is 32-char alnum, differs from old
- Live API test with new credential: `/quote` HTTP 200; historical, profile, fundamentals, analyst endpoints OK
- Found: `/news/stock-latest` returns HTTP 402 (Payment Required) — new key's plan lacks news endpoint (affects app.py news tab only)
- PROJECT_CONTEXT.md updated (Section 20); no credential value written anywhere
- No git history modification; no commits; no force-push
**Tests**: Live FMP API validation (masked, no key output)
**Results**: New credential works; app.py news tab degraded (402); incident mostly closed
**Problems**: News endpoint requires higher FMP plan; history rewrite still pending approval
**Decisions**: No history rewrite without approval; .env perms 600; news fix deferred
**Backup**: post-rotation secure checkpoint (see Section 17)
**Next step**: Await approval on history rewrite; optionally fix app.py news; resume Phase 1

### 2026-08-11 23:40 — SECURITY INCIDENT RESPONSE
**Goal**: Assess and document FMP API key exposure in git history
**Work completed**:
- Confirmed working tree: no hardcoded key in source; `.env` git-ignored (`.gitignore:2`)
- Located exposure: 6 commits on main (all pushed to public origin/main); root + engines/core_fmp.py; no dangling commits; no other files
- No key values printed/displayed anywhere
- Documented incident in PROJECT_CONTEXT.md (Section 20)
- Git history NOT modified (awaiting approval)
- Emergency checkpoint backup created (pre-history-rewrite recovery point)
**Tests**: None (no code changed)
**Results**: Incident fully mapped; remediation of working tree confirmed; history remediation pending approval + key rotation
**Problems**: Credential was public → rotation mandatory; force-push affects all clones; GitHub secret scan may flag
**Decisions**: Do not rewrite history without approval; do not commit working-tree Phase 1 changes until incident closed
**Backup**: US-stocks_2026-08-11_23-23.tar.gz preserved + emergency checkpoint (see Section 17)
**Next step**: Await user approval: (1) rotate key, (2) approve history rewrite

### 2026-08-11 23:23
**Goal**: Complete Phase 1 - Configuration Externalization + Security Fix
**Work completed**:
- Verified prior in-progress Phase 1 state (config.yaml + sentinel/config.py existed, undocumented)
- Fixed sentinel/config.py default config path bug (pointed to sentinel/config.yaml, now root config.yaml)
- Created .gitignore (protects .env, .streamlit/secrets.toml, caches, results, __pycache__, venv, AUDIT_REPORT.md)
- Updated .env.sample with FMP_API_KEY; created local .env (untracked) with existing key
- **SECURITY**: Removed hardcoded FMP API key from core_fmp.py:11 + engines/core_fmp.py:11 (env-only, dotenv loading added)
- Added pydantic, python-dotenv, PyYAML to requirements.txt
- Verified: config loads root config.yaml values; sentinel.py full scan OK (310 tickers, 30 qualified, 15 ACTION, 82.9s); all engines import OK; no hardcoded key in code
- Updated PROJECT_CONTEXT.md to reflect real state
**Files changed**: sentinel/config.py (fix), .gitignore (new), .env.sample, .env (new, untracked), core_fmp.py, engines/core_fmp.py, requirements.txt, PROJECT_CONTEXT.md
**Tests**: None exist (pytest not set up); verified via py_compile + import checks + full sentinel scan
**Results**: Phase 1 config externalization + security fix complete; scanner operational with new config system
**Problems**: FMP key still exposed in git history (rotation recommended); engines not yet migrated to injected Config (backward-compat wrapper used)
**Decisions**: Keep backward-compat wrapper (config.py) so engines stay functional; migrate engines in Phase 2
**Backup**: US-stocks_2026-08-11_23-23.tar.gz (see section 17)
**Next step**: Complete Phase 1 remaining items (key rotation, pytest setup, commit)

### 2026-08-11 22:30
**Goal**: Initial project setup, installation, audit, and documentation
**Work completed**:
- Cloned repository to ~/Projects/US-stocks/
- Created virtual environment, installed dependencies
- Ran sentinel.py (full scan: 170s, 315 tickers, 30 qualified, 15 ACTION)
- Launched both Streamlit apps successfully
- Performed comprehensive audit (architecture, financial logic, performance)
- Generated AUDIT_REPORT.md
- Moved project to correct location (~/Projects/US-stocks/)
- Created PROJECT_CONTEXT.md (this file)
- Created AI_INSTRUCTIONS.md
- Created initial external backup (US-stocks_2026-08-11_22-30.tar.gz)
- Verified backup integrity
**Files changed**: AUDIT_REPORT.md (new), PROJECT_CONTEXT.md (new), AI_INSTRUCTIONS.md (new)
**Tests**: None exist
**Results**: All systems operational, audit complete, backup verified
**Problems**: Hardcoded API key, scattered config, no tests, delisted tickers, VCP pivot issue, look-ahead bias
**Decisions**: Follow Master Project System for organization, backup, continuity
**Backup**: US-stocks_2026-08-11_22-30.tar.gz (verified)
**Next step**: Implement Phase 1 - Configuration Externalization + Security Fix