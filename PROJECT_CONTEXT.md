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

### RS Calculation — RSIndicator (engines/analysis.py:12-102)
```python
# Configurable weighted momentum across N timeframes (default: 4)
# Windows and weights are read from config.yaml `rs:` section
rs = RSIndicator()  # loads windows=[252,126,63,21], weights=[0.4,0.2,0.2,0.2]
raw_rs = rs.compute_raw(df)  # returns weighted sum of period returns

# Fallback: if data < window, uses c[-1] / c[0] - 1
# Insufficient data (< min_data_days=21) returns ERROR_SENTINEL = -999.0

# Percentile ranking within universe (1-99)
rs.compute_percentiles(raw_list)  # sorts by raw_rs, assigns rs_rating
```

**Configuration** (config.yaml `rs:` section):
| Parameter | Default | Description |
|-----------|---------|-------------|
| windows | [252, 126, 63, 21] | Lookback windows in trading days (12m, 6m, 3m, 1m) |
| weights | [0.4, 0.2, 0.2, 0.2] | Weight per window (must sum to 1.0) |
| min_data_days | 21 | Minimum data required; below → ERROR_SENTINEL |

**API**:
- Instance: `RSIndicator(windows=..., weights=..., min_data_days=...)`
- `compute_raw(df) → float` — raw weighted-momentum score
- `compute_percentiles(raw_list) → list[dict]` — in-place sort + rs_rating assignment
- Classmethods (backward-compat): `RSIndicator.get_raw_score(df)`, `RSIndicator.assign_percentiles(raw_list)`

**Backward compatibility**: `RSAnalyzer` is a thin static wrapper delegating to `RSIndicator` with default config. Existing callers (`sentinel.py`, `ecr_strategy.py`, `app2.py`) produce identical results.

### VCP Scoring — VCPIndicator (engines/analysis.py:104-260) - Max 105 points
```python
# Configurable VCP scoring — reads from config.yaml vcp: section
vcp = VCPIndicator()  # loads tightness_periods, volume_lookback, ma_periods, etc.
result = vcp.calculate(df)  # returns score, atr, signals, breakdown
```

| Component | Weight | Logic |
|-----------|--------|-------|
| Tightness | 40pt | Price range % over configurable periods (default 20/30/40/60d); contraction = short < mid < long |
| Volume Dry-up | 30pt | short_vol / long_vol (gap-separated); <0.45 = 30pt |
| MA Alignment | 30pt | Price>MA_short (10), MA_short>MA_mid (10), MA_mid>MA_long (10) |
| Pivot Bonus | 5pt | Distance to pivot high: 0-4% = 5pt, 4-8% = 3pt |

**Configuration** (config.yaml `vcp:` section):
| Parameter | Default | Description |
|-----------|---------|-------------|
| tightness_periods | [20, 30, 40, 60] | Periods for range calculation |
| volume_lookback_short | 20 | Short-term volume window |
| volume_lookback_long | 60 | Long-term volume window start |
| volume_lookback_gap | 20 | Gap between short and long windows |
| ma_periods | [50, 150, 200] | Moving average periods |
| pivot_near_pct | 0.04 | Near pivot threshold (5pt bonus) |
| pivot_far_pct | 0.08 | Far pivot threshold (3pt bonus) |
| max_tightness_score | 40 | Max tightness points |
| max_volume_score | 30 | Max volume points |
| max_ma_score | 30 | Max MA alignment points |

**API**:
- Instance: `VCPIndicator(tightness_periods=..., ma_periods=..., ...)`
- `calculate(df) → dict` — returns {score, atr, signals, is_dryup, range_pct, vol_ratio, breakdown}

**Backward compatibility**: `VCPAnalyzer` is a thin static wrapper delegating to `VCPIndicator` with default config. Existing callers (`sentinel.py`, `ecr_strategy.py`, `app2.py`) produce identical results.

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
- ✅ **PHASE 2 COMPLETE (2026-08-12)** — all indicator refactors regression-free; 132 tests passing; golden baseline preserved; see Sections 2.2–2.5 status

### Phase 2.2 Status (2026-08-12)
**✅ ALL MILESTONES COMPLETE — RSIndicator Implementation + Documentation Verified**:
- 2.2.0 Discovery: ✅ Complete
- 2.2.1 Design: ✅ Complete
- 2.2.2 Implementation: ✅ CHECKPOINT APPROVED
- 2.2.3 Regression: ✅ Complete (9/9 pass)
- 2.2.4 Documentation: ✅ Complete
- 2.2.5 Final verification: ⏳ Pending
- Status: MILESTONE 2.2.2 — CHECKPOINT APPROVED (implementation + verification gate passed)
- Objective: Refactor RS calculation into a configurable, testable component without changing behavior — ACHIEVED
- HEAD commit: `066c948`
- Pre-phase backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase2_2.tar.gz` (verified, 43 files, 78KB)
- Checkpoint backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase2_2-checkpoint.tar.gz` (verified, 43 files, 81KB — contains all Phase 2.2.2 changes)
- Files changed:
  - `engines/analysis.py` — added `RSIndicator` class (configurable windows/weights, validation, backward-compat classmethods); `RSAnalyzer` now a thin wrapper delegating to `RSIndicator`
  - `tests/test_analysis.py` — added 17 new tests (RSIndicator config, compute_raw, compute_percentiles, NaN/None, backward compat)
  - `PROJECT_CONTEXT.md` — updated with Phase 2.2.2 status, testing, session log, backup state
- Architecture changes:
  - `RSIndicator` reads from existing `config.yaml` `rs:` section (previously unused by RSAnalyzer)
  - Constructor accepts optional `windows`, `weights`, `min_data_days` (defaults from config)
  - Validation: weights sum to 1.0, windows/weights length match, min_data_days >= 1
  - `RSAnalyzer` preserved as static wrapper — zero behavioral change for existing callers (`sentinel.py`, `ecr_strategy.py`, `app2.py`)
- Configuration: config.yaml `rs:` section (windows: [252,126,63,21], weights: [0.4,0.2,0.2,0.2] sum=1.0, min_data_days: 21) now wired to RSIndicator
- Backward compatibility: VERIFIED — RSAnalyzer.get_raw_score() ≡ RSIndicator.get_raw_score(); RSAnalyzer.assign_percentiles() ≡ RSIndicator.assign_percentiles()
- Tests: **66 passed** (49 original + 17 new), full suite green (~172s)
- Regression: **9/9 passed** — golden replay reproduces Phase 2.1 baseline exactly (310 scanned / 30 qualified / 15 ACTION)
- Known issues: None
- Documentation: Section 8 (Algorithms) updated to describe RSIndicator, config.yaml `rs:` section, API, and backward compatibility
- README.md updated: repository structure mentions RSIndicator; Configuration section includes RS example; Project Status reflects Phase 2.2 completion; test count updated to 66
- Docs backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase2_2-docs.tar.gz` (verified, 43 files, 82KB)
- Next milestone: MILESTONE 2.2.5 (Final verification) → STOP

### Phase 2.3 Status (2026-08-12)
**🔄 IN PROGRESS — VCPAnalyzer → VCPIndicator Refactor**:
- Status: MILESTONE 2.3.2 (Implementation) — VCPIndicator introduced
- Objective: Refactor VCP calculation into a configurable, testable component without changing behavior
- HEAD commit: `8255b8e`
- Pre-phase backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase2_3.tar.gz` (verified, 43 files, 82KB)
- Checkpoint backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase2_3-checkpoint.tar.gz` (verified, 43 files, 83KB)
- Files changed:
  - `engines/analysis.py` — added `VCPIndicator` class (configurable tightness_periods/volume_lookback/ma_periods/pivot thresholds, validation, backward-compat classmethod); `VCPAnalyzer` now a thin wrapper delegating to `VCPIndicator`
  - `tests/test_analysis.py` — added 12 new tests (VCPIndicator config, calculate, validation, edge cases, backward compat)
- Architecture changes:
  - `VCPIndicator` reads from existing `config.yaml` `vcp:` section (previously unused by VCPAnalyzer)
  - Constructor accepts optional overrides for all configurable parameters
  - Validation: tightness_periods >= 2, ma_periods >= 2, pivot_far_pct > pivot_near_pct, etc.
  - `VCPAnalyzer` preserved as static wrapper — zero behavioral change for existing callers (`sentinel.py`, `ecr_strategy.py`, `app2.py`)
- Configuration: config.yaml `vcp:` section now wired to VCPIndicator (schema unchanged)
- Backward compatibility: VERIFIED — VCPAnalyzer.calculate() ≡ VCPIndicator.calculate()
- Tests: **78 passed** (66 previous + 12 new), full suite green (~196s)
- Regression: **9/9 passed** — golden replay reproduces Phase 2.1 baseline exactly
- Known issues: None
- Next step: MILESTONE 2.3.3 (Documentation) → 2.3.4 (Final verification) → STOP

### Phase 2.4 Status (2026-08-12)
**✅ MILESTONE 2.4.2E COMPLETE — StrategyValidator walk-forward** (2026-08-12):
- Objective: Refactor StrategyValidator so walk-forward evaluation is point-in-time and does not use future bars, while preserving existing behavior for legacy callers — ACHIEVED
- Implementation (already committed in WIP checkpoint `40bb38a`):
  - `_point_in_time_indicators(df, bar_idx)`: computes ATR(14), MA50, pivot at bar_idx using only `df.iloc[:bar_idx+1]` — structural look-ahead guard
  - `evaluate_walk_forward(df, min_bars_for_entry=200, lookback_bars=250)`: point-in-time backtest using `_point_in_time_indicators()` for entry decisions; returns {profit_factor, trades, start, evaluated_bars}
  - `run_walk_forward(df, min_bars_for_entry=200, lookback_bars=250)`: convenience wrapper returning float profit_factor
  - Legacy `run()` preserved byte-for-byte unchanged — sentinel.py/app2.py production path unaffected
- Tests (9 walk-forward tests, all passing):
  - `test_walk_forward_api_compat`: API exists and returns correct types
  - `test_walk_forward_evaluation_result`: output structure validated
  - `test_walk_forward_deterministic`: identical inputs → identical outputs
  - `test_walk_forward_empty_insufficient_data`: None/short frame → 1.0
  - `test_walk_forward_atr_uses_only_available_bars`: ATR(14) at bar t equals ATR on truncated frame
  - `test_walk_forward_point_in_time_isolation`: future bars don't affect indicators
  - `test_walk_forward_no_future_bar_leakage`: bar limits verified at multiple indices
  - `test_walk_forward_detects_lookahead`: synthetic spike frame distinguishes clean vs biased
  - `test_walk_forward_matches_legacy_run`: walk-forward matches legacy run() on normal data
- Regression: **9/9 passed** — golden replay reproduces Phase 2.1 baseline exactly
- Full suite: **132 passed** (366s)
- Golden artifact `tests/golden/baseline_2026-08-12.json`: UNCHANGED byte-for-byte
- Backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase2_4-2e-checkpoint.tar.gz` (verified, 93KB, 41 files)
- Known issues: None
- Next step: STOP — Phase 2.4.2 complete (A through E all done); await authorization for Phase 2.4.3 regression

**✅ MILESTONE 2.4.3 COMPLETE — Regression Gate** (2026-08-12):
- Objective: Verify all Phase 2.4.2 changes produce no regressions — ACHIEVED
- Regression gate (`pytest tests/test_regression.py -v`): **9/9 passed** (159s)
  - `test_golden_artifact_exists`: golden JSON present
  - `test_golden_artifact_contains_no_secrets`: no credentials in golden
  - `test_golden_baseline_counts_matches_approved_baseline`: 310/30/15, commit b5b0986
  - `test_golden_universe_matches_config`: universe count matches config.TICKERS
  - `test_frozen_scan_reproduces_golden`: fresh run == golden exactly
  - `test_frozen_scan_is_deterministic`: two runs identical
  - `test_frozen_scan_matches_live_reference_decisions`: frozen replay == live 2026-08-12 decisions
  - `test_qualified_is_action_superset_in_golden`: selected ⊆ qualified
  - `test_ranking_order_present_in_golden`: (status_rank, score) ordering correct
- Full suite: **132 passed** (179s)
- Golden artifact `tests/golden/baseline_2026-08-12.json`: UNCHANGED byte-for-byte (sha256: `1bf2f37...`)
- Decision fields verified: 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- config.yaml: NOT modified
- Golden baseline: NOT modified
- Backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase2_4-3-regression-gate.tar.gz` (verified, 93KB, 41 files)
- Known issues: None
- **Phase 2.4 COMPLETE** — all milestones (2.4.2A–E + 2.4.3) verified and passed

### Phase 2.5 Status (2026-08-12)
**✅ MILESTONE 2.5 COMPLETE — Phase 2 Closeout & Final Verification** (2026-08-12):
- Objective: Final verification that all Phase 2 indicator refactors are regression-free and documentation is current — ACHIEVED
- Full suite (`pytest --tb=short`): **132 passed** (174s), 0 failed, 0 skipped
- Regression gate (`pytest tests/test_regression.py -v --tb=short`): **9/9 passed** (162s)
- Golden artifact `tests/golden/baseline_2026-08-12.json`: UNCHANGED byte-for-byte (sha256: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`)
- 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- Decision fields verified: status, entry, stop, target, shares, sector, rs, vcp, pf all match golden exactly
- config.yaml: NOT modified
- Golden baseline: NOT modified
- No production code changes (documentation-only milestone)
- **Phase 2 COMPLETE** — all milestones (2.1–2.5) verified and passed

### Phase 3 Status (2026-08-12)
**✅ COMPLETE — Strategies Layer** (closed 2026-08-13):
- Phase 3 Discovery: ✅ Complete
- Slice 3.1 (Strategy package structure): ✅ COMPLETE
- Slice 3.2 (RelativeStrengthRanking): ✅ COMPLETE (committed `f607c76`)
- Slice 3.3 (VCPBreakoutStrategy): ✅ COMPLETE (committed `f6d11c2`)
- Slice 3.4 (MinerviniTrendTemplate): ✅ COMPLETE (committed `a3ba4f9`)
- Slice 3.5 (Regression/test gate): ✅ COMPLETE (verified 2026-08-13)
- Slice 3.6 (Documentation + closeout): ✅ COMPLETE (committed)

**✅ SLICE 3.6 COMPLETE — Documentation + Phase 3 Closeout** (2026-08-13):
- Objective: Document verified Phase 3 facts and close out the Strategies Layer — ACHIEVED
- Phase 3 milestones (all verified):
  - **3.1 Strategy package**: `engines/strategies/base.py` — canonical `Strategy` ABC; backward-compatible re-export through `engines.analysis`
  - **3.2 RelativeStrengthRanking**: additive/opt-in `engines/strategies/rs_ranking.py` — weighted momentum ranking, benchmark support (SPY default), percentile ranking (1-99); NOT a replacement for RSIndicator
  - **3.3 VCPBreakoutStrategy**: additive/opt-in `engines/strategies/vcp_breakout.py` — composes `VCPIndicator(use_contraction_pivot=True)`, contraction pivot detection, breakout confirmation (close > pivot AND volume surge), entry/stop/target, own score scale (never fed into sentinel.py)
  - **3.4 MinerviniTrendTemplate**: additive/opt-in `engines/strategies/minervini_template.py` — 9-point trend template, configurable criteria, look-ahead-free (trailing-only), minimum historical data requirement (252 bars), entry/stop/target
  - **3.5 Regression Gate**: full suite **169 passed**, 0 failed, 0 skipped; regression **9/9 passed**; golden unchanged (SHA256 `1bf2f37a...`); 310 scanned / 30 qualified / 15 ACTION; decision fields bit-identical
- The three new strategy components (RelativeStrengthRanking, VCPBreakoutStrategy, MinerviniTrendTemplate) are OPT-IN and are NOT wired into sentinel.py — sentinel.py behavior is preserved
- config.yaml was NOT modified during Phase 3
- Final test count: **169 tests** passing
- Golden SHA256: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- Pre-closeout backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase3_6.tar.gz` (verified, 6.6MB, 464 files)
- Final checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase3-final.tar.gz` (verified)
- Known issues: None
- **Phase 3 COMPLETE** — all milestones (3.1-3.6) verified and passed
- Next step: Phase 4 Discovery (await authorization; no Phase 4 details invented here)

### Phase 4 Status (2026-08-13)
**Phase 4 — Filters & Ranking (roadmap §11: "Liquidity, MarketCap, Sector, Fundamental filters") — IN PROGRESS**
- Phase 4 Discovery: ✅ COMPLETE (2026-08-13) — recommended scope: library-only `FilterEngine`, NOT wired into sentinel.py (Phase 6 owns the pipeline refactor)
- Slice 4.1 (Filter framework + config schema): ✅ COMPLETE (committed `d4aed14`)
- Remaining slices: 4.2 data enrichment, 4.3 Liquidity+MarketCap filters, 4.4 Sector filter, 4.5 Fundamental filters, 4.6 ranking (optional), 4.7 regression gate, 4.8 documentation/closeout

**✅ SLICE 4.1 COMPLETE — Filter framework + filters config schema** (2026-08-13, verified 2026-08-13):
- Objective: Add the opt-in, disabled-by-default Phase 4 filter framework and its config schema — ACHIEVED
- `engines/filters.py` (NEW): `Filter` ABC (`name`/`stage`/`check`), `FilterEngine` registry + execution pipeline, `FilterContext`/`FilterResult` value types; `STAGE_UNIVERSE` (before RS ranking) and `STAGE_CANDIDATE` (post-technical) stage constants; `from_config()` reads the Pydantic config; `_build_filters()` currently returns `[]` (concrete filters land in slices 4.3-4.5)
- Default behavior: `FilterEngine` is an identity pass-through unless `enabled=True`; disabled engines return inputs unchanged with empty rejection lists (golden-safe)
- `sentinel/config.py`: added `FilterConfig` (+ `LiquidityFilterConfig`, `MarketCapFilterConfig` with min≤max validation, `SectorFilterConfig` with include/exclude disjoint validation, `FundamentalFilterConfig`) wired into `Config.filters` (default factory, disabled)
- `config.yaml`: NEW additive `filters:` section — `enabled: false`, all thresholds `null`/empty (documented)
- `config.py` CONFIG dict NOT changed (FilterEngine reads the Pydantic config directly; no legacy bridge key needed)
- Tests: `tests/test_filters.py` (NEW, 25), `tests/test_config.py` (23→29, +6 FilterConfig), `tests/test_imports.py` CORE_MODULES now includes `engines.filters`
- Full suite: **200 passed**, 0 failed, 0 skipped (regression 9/9 executed, 100s)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION preserved by default; sentinel.py untouched
- `git diff --check`: CLEAN; committed `d4aed14`
- Pre-Phase 4 backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase4.tar.gz` (verified, 114KB, 48 files, source-only)
- Known issues: None
- Next step: STOP — await authorization for slice 4.2 (data enrichment: FundamentalEngine additive fields + OHLCV liquidity helper)

**✅ SLICE 4.2 COMPLETE — Data enrichment for filters** (verified 2026-08-14):
- Objective: Add the additive data inputs Phase 4 filters need — `FundamentalEngine` enrichment fields and an OHLCV-derived liquidity helper — without any behavior change — ACHIEVED
- `engines/fundamental.py`: `FundamentalEngine.get()` now returns 5 additive keys (pre-existing keys/values untouched): `market_cap`, `average_volume`, `average_volume_10d`, `shares_outstanding`, `float_shares` (all `None` when `.info` lacks them; JSON-cached like the rest)
- `engines/data.py`: NEW `DataEngine.get_liquidity_metrics(df, lookback=20)` — trailing-only, look-ahead-free average dollar volume + average volume from the last N bars; returns `{"avg_dollar_volume", "avg_volume"}` with `None` on empty/missing-column/invalid-lookback; pandas skipna semantics; never raises
- NOT committed (awaiting user commit authorization per slice 4.2 rules)
- Tests: `tests/test_data.py` (NEW, 11) + `tests/test_fundamental.py` (NEW, 8)
- Full suite: **219 passed**, 0 failed, 0 skipped (regression 9/9 executed, 188s)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION preserved by default; sentinel.py and StrategyValidator untouched; config.yaml NOT modified this slice
- `git diff --check`: CLEAN (4 files: 2 modified engines, 2 new test files)
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase4_2.tar.gz` (verified, 121KB, 50 files)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase4_2-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — await authorization for slice 4.3 (Liquidity + MarketCap filters)

**✅ SLICE 4.3 COMPLETE — Liquidity + MarketCap filters** (verified 2026-08-14):
- Objective: Implement the first two concrete universe-stage filters (liquidity, market cap) and wire them into `FilterEngine.from_config()` — ACHIEVED
- `engines/filters.py`: NEW `LiquidityFilter` (min avg dollar volume + min avg volume; OHLCV-derived via `DataEngine.get_liquidity_metrics`, volume falls back to profile `average_volume`; missing data default-passes) and `MarketCapFilter` (min/max USD, inclusive bounds, applied to `ctx.profile["market_cap"]`; missing data default-passes), both `STAGE_UNIVERSE`; `_build_filters()` now constructs a filter only when a threshold is configured (all-None sections yield none), order: liquidity → market cap
- `config.yaml`: unchanged this slice (existing `filters:` section from 4.1 already covers both)
- Filters remain disabled by default (`filters.enabled: false`) — identity pass-through preserved
- NOT committed (awaiting user commit authorization)
- Tests: `tests/test_filters.py` 25→45 (+20: LiquidityFilter 8, MarketCapFilter 7, from_config wiring 5)
- Full suite: **239 passed**, 0 failed, 0 skipped (regression 9/9 executed, 194s)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION preserved by default; sentinel.py, StrategyValidator, golden artifact untouched
- `git diff --check`: CLEAN (2 files modified: engines/filters.py, tests/test_filters.py)
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase4_3.tar.gz` (verified, 124KB, 52 files)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase4_3-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — await authorization for slice 4.4 (Sector filter)

**✅ SLICE 4.4 COMPLETE — Sector filter** (verified 2026-08-14):
- Objective: Implement the universe-stage Sector filter (include/exclude), resolving the "filter before RS ranking" known problem — ACHIEVED
- `engines/filters.py`: NEW `SectorFilter` (case-insensitive + trimmed include/exclude; reads `ctx.sector`, falls back to `ctx.profile["sector"]`; empty include = all sectors allowed; missing sector default-passes), `STAGE_UNIVERSE`; `_build_filters()` now constructs it when include/exclude non-empty, order: liquidity → market_cap → sector
- `sentinel/config.py` + `config.yaml`: unchanged (SectorFilterConfig schema with disjoint validation already present from 4.1; filters.enabled remains false)
- NOT committed (awaiting user commit authorization)
- Tests: `tests/test_filters.py` 45→62 (+17: SectorFilter unit 11, from_config wiring 6)
- Full suite: **256 passed**, 0 failed, 0 skipped (regression 9/9 executed)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION preserved by default; sentinel.py, StrategyValidator, golden artifact untouched
- `git diff --check`: CLEAN (2 files modified: engines/filters.py, tests/test_filters.py)
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase4_4.tar.gz` (verified, 124KB, 52 files)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase4_4-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — await authorization for slice 4.5 (Fundamental filter)

**✅ SLICE 4.5 COMPLETE — Fundamental filter** (verified 2026-08-14):
- Objective: Implement the universe-stage Fundamental filter from the existing growth/valuation fields and config schema — ACHIEVED
- `engines/filters.py`: NEW `FundamentalFilter` (thresholds: `min_revenue_growth`, `min_earnings_growth` as decimal ratios; `max_forward_pe` incl. non-positive-PE rejection when configured; `min_analyst_count`), reads `ctx.profile` keys as populated by `FundamentalEngine.get` (`revenue_growth`, `earnings_growth`, `pe_forward`, `analyst_count`); missing fields default-pass; `_build_filters()` order now liquidity → market_cap → sector → fundamental
- `sentinel/config.py` + `config.yaml`: unchanged (FundamentalFilterConfig schema already present from 4.1; filters.enabled remains false)
- NOT committed (awaiting user commit authorization)
- Tests: `tests/test_filters.py` 62→84 (+22: FundamentalFilter unit 17, from_config wiring 5)
- Full suite: **278 passed**, 0 failed, 0 skipped (regression 9/9 executed)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION preserved by default; sentinel.py, StrategyValidator, golden artifact untouched
- `git diff --check`: CLEAN (2 files modified: engines/filters.py, tests/test_filters.py)
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase4_5.tar.gz` (verified, 124KB, 52 files)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase4_5-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — await authorization for slice 4.6 (Phase 4 closure: engine execution integration tests)

**✅ SLICE 4.6 COMPLETE — Phase 4 closure: integration tests** (verified 2026-08-14):
- Objective: Add engine-execution integration tests proving universe/candidate-stage semantics and framework guarantees — ACHIEVED (additive only; no engine code change required)
- `engines/filters.py`: UNCHANGED — integration tests exposed no defects; hardening policy ("fix only test-exposed issues") triggered no changes, so default behavior is byte-identical
- `tests/test_filters.py` 84→96 (+12 integration tests covering the full 10-item scope: universe-stage execution, filter ordering liquidity→market_cap→sector→fundamental, short-circuit on first failure, universe-before-candidate stage semantics, candidate-stage isolation, disabled-engine exact identity, enabled-no-filters identity, missing-data default-pass (bare/empty-df/empty-profile/no-provider), deterministic aggregated rejection reasons, no input mutation (list+tuple), deterministic repeated execution (3 runs deep-equal), default config.yaml engine is disabled no-op)
- NOT committed (awaiting user commit authorization)
- Full suite: **290 passed**, 0 failed, 0 skipped (regression 9/9 executed, 178s)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION preserved; sentinel.py, StrategyValidator, config.yaml, golden artifact untouched
- `git diff --check`: CLEAN (1 file modified: tests/test_filters.py)
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase4_6.tar.gz` (verified, 124KB, 52 files)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase4_6-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — await authorization for slice 4.7 (Phase 4 finalization: commit + phase close record)

### Phase 5 Status (2026-08-14)
**Phase 5 — Backtesting (roadmap §11: "Walk-forward, purged k-fold, OOS validation") — IN PROGRESS**
- Phase 5.1 (BacktestEngine): ✅ COMPLETE (verified 2026-08-14, committed `dc1c775`)
- Phase 5.2 (Purged K-Fold CV): ✅ COMPLETE (verified 2026-08-14, committed `b11d9c3`)
- Phase 5.3 (OOS Validation): ✅ FINAL VERIFICATION COMPLETE (verified 2026-08-14, NOT yet committed)
- Next slices: 5.4+ — NOT STARTED (await authorization)

**✅ SLICE 5.1 COMPLETE — BacktestEngine** (verified 2026-08-14, committed `dc1c775`):
- `engines/backtest.py` (NEW): `BacktestEngine(lookback_bars=250, min_bars_for_entry=50, risk_pct=0.015, initial_capital=100_000.0)` reading defaults from config.yaml `backtest:` section; `run(strategy, df) -> dict` and `evaluate_at(strategy, df, bar_idx) -> dict`; strict trailing-only (`df.iloc[:t+1]`), deterministic, additive (no wired-in use)
- Safety: `insufficient_data`/`missing_ohlc_columns` guard → zero-trade safe record (pf 1.0, empty trades); never raises; no input/strategy mutation (strategy deep-copied); same-instant same-index strategy decisions are point-in-time (future bars do not affect past decisions)
- Stop/target: order = stop (low ≤ stop → −1.0 R) then target (high ≥ target → +R); end-of-data partial exit uses close; per-trade compounding at `risk_pct` of current equity; max drawdown vs running peak
- Metrics schema (`RESULT_KEYS`): profit_factor, trades, n_trades, win_rate, total_return_pct, annualized_return_pct, max_drawdown_pct, start, evaluated_bars, insufficient_data, reason
- Tests: `tests/test_backtest.py` (NEW, 17); `tests/test_imports.py` CORE_MODULES now includes `engines.backtest`
- Full suite **307 passed**; regression **9/9 passed**; golden SHA256 unchanged `1bf2f37ab...`; 310/30/15 preserved

**✅ SLICE 5.2 COMPLETE — Purged K-Fold CV** (verified 2026-08-14):
- Objective: Add purged k-fold cross-validation to `BacktestEngine` — deterministic folds, configurable purge gap, configurable embargo window, strictly no train/test temporal leakage, additive (existing `run()`/`evaluate_at` unchanged) — ACHIEVED
- `engines/backtest.py`: `run()` refactored to delegate its simulation loop to internal `_simulate(local, df, start_bar, end_bar)` — behavior byte-identical (17 Phase 5.1 tests still green). NEW `fold_bounds(n_bars, n_folds, purge_gap, embargo, min_bars_for_entry)` — deterministic contiguous test blocks; fold i covers `[i*n//k, (i+1)*n//k - 1]`, eval window `[max(fold_start + purge_gap, min_bars_for_entry), fold_end - embargo]`. NEW `cross_validate(strategy, df, n_folds=5, purge_gap=0, embargo=0)` — runs each fold on a fresh deep copy of the strategy, closes positions still open at `eval_end` with an end-of-window partial exit (labels confined to the fold), marks undersized folds `fold_too_small`, returns per-fold records + `mean_profit_factor`/`mean_total_return_pct`
- No-leakage guarantees (all test-verified): consecutive folds' evaluated bars are strictly non-overlapping and separated by exactly `purge_gap + embargo` bars; a trade entered in one fold is always closed at or before that fold's `eval_end`; no strategy state flows between folds (per-fold deepcopy)
- Schema: `CV_KEYS` (n_folds, purge_gap, embargo, insufficient_data, reason, fold_bounds, folds, mean_profit_factor, mean_total_return_pct); each fold record = `RESULT_KEYS` + (fold, test_start, test_end, eval_start, eval_end) via `FOLD_RECORD_KEYS`
- Validation: `n_folds >= 2`, `purge_gap >= 0`, `embargo >= 0` (else ValueError); `None`/short/empty/missing-OHLC inputs return a safe `insufficient_data`/`missing_ohlc_columns` record
- Tests: `tests/test_backtest.py` 17→35 (+18: importability, param validation, insufficient-data safety, fold count/boundaries, purge-gap enforcement, embargo enforcement, no-overlap between folds, determinism, schema, end-of-window partial-exit label confinement, embargo-shortened exit, in-fold stop, fold-too-small safety, mixed valid/too-small, no input/strategy mutation, real `VCPBreakoutStrategy` smoke)
- NOT committed (awaiting user commit authorization)
- Full suite (`pytest --tb=short`): **325 passed**, 0 failed, 0 skipped (243s)
- Regression (`pytest tests/test_regression.py -v --tb=short`): **9/9 passed** (207s)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- `git diff --check`: CLEAN (2 files: engines/backtest.py modified, tests/test_backtest.py modified)
- Forbidden files untouched: sentinel.py, config.yaml, engines/analysis.py, `StrategyValidator.run()`, golden artifact
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase5_2.tar.gz` (verified, gzip OK)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase5_2-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — report state; Phase 5.3 NOT started (await authorization)

**✅ SLICE 5.3 COMPLETE — Out-of-Sample Validation** (verified 2026-08-14):
- Objective: Add explicit out-of-sample validation to `BacktestEngine` — train / validation / test temporal separation, configurable split boundaries, strictly no future-bar leakage, deterministic metrics/schema, additive (existing `run()`/`evaluate_at()`/`cross_validate()` unchanged) — ACHIEVED
- `engines/backtest.py`: NEW `oos_split(n_bars, train_frac=0.6, validation_frac=0.2, test_frac=0.2)` — deterministic split; `n_train = round(n*train_frac)`, `n_val = round(n*validation_frac)`, test absorbs rounding so the three segments are disjoint, contiguous, and cover every bar exactly once. NEW `validate_oos(strategy, df, train_frac, validation_frac, test_frac)` — simulates each segment independently on a fresh deep copy via the shared `_simulate`, confined to its own bar range (end-of-window partial exit → no label crosses segment boundaries, no evaluated bar reads a future bar); returns `segments` (train/validation/test records) + `out_of_sample` (= test record) + `mean_profit_factor`/`mean_total_return_pct` over valid segments
- Per-segment eval window = `[max(segment_start, min_bars_for_entry), segment_end]`; non-empty-but-too-short segments → `segment_too_small`, zero-width segments (e.g. `validation_frac=0`) → `empty_segment`, both safe zero-trade records
- Validation: all fractions >= 0, sum == 1.0 (else ValueError), `test_frac > 0`; `None`/short/empty/missing-OHLC → safe `insufficient_data`/`missing_ohlc_columns` record
- Schema: `OOS_KEYS` (train_frac, validation_frac, test_frac, n_bars, train/validation/test start+end, insufficient_data, reason, segments, out_of_sample, mean_profit_factor, mean_total_return_pct); each segment record = `RESULT_KEYS` + (segment, segment_start, segment_end, eval_start, eval_end) via `OOS_SEGMENT_KEYS`
- Tests: `tests/test_backtest.py` 35→51 (+16: importability, split correctness incl. no-validation-segment and covers-every-bar-exactly-once, param validation, insufficient-data safety, temporal ordering, future-spike no-leakage (train/validation invariant to later spikes), determinism, schema, disjoint+confined segment evals, empty-segment, segment-too-small, no input/strategy mutation, real `VCPBreakoutStrategy` smoke)
- NOT committed (awaiting user commit authorization)
- Full suite (`pytest --tb=short`): **341 passed**, 0 failed, 0 skipped (249s)
- Regression (`pytest tests/test_regression.py -v --tb=short`): **9/9 passed** (193s)
- Golden SHA256 unchanged: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`
- 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- `git diff --check`: CLEAN (2 files: engines/backtest.py modified, tests/test_backtest.py modified)
- Forbidden files untouched: sentinel.py, config.yaml, engines/analysis.py, `StrategyValidator.run()`, golden artifact
- Pre-slice backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_pre-phase5_3.tar.gz` (verified, gzip OK)
- Checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-14_phase5_3-checkpoint.tar.gz` (verified, gzip OK)
- Known issues: None
- Next step: STOP — report state; Phase 5.4 NOT started (await authorization)

**✅ SLICE 3.5 COMPLETE — Full Test + Regression Gate** (2026-08-13):
- Objective: Prove all Phase 3 strategy additions (Strategy ABC, RelativeStrengthRanking, VCPBreakoutStrategy, MinerviniTrendTemplate) remain fully backward-compatible and the Phase 2 golden baseline is unchanged — ACHIEVED
- Tests (all executed this session, no existing reports reused):
  - `tests/test_analysis.py` → **116 passed** (0 failed, 0 skipped)
  - `tests/test_config.py` → **23 passed**
  - `tests/test_fmp.py` → **18 passed**
  - `tests/test_imports.py` → **3 passed**
  - `tests/test_regression.py -v` → **9/9 passed** (executed, 152s)
  - Full suite `pytest --tb=short` → **169 passed**, 0 failed, 0 skipped (164s, exit 0)
- Golden artifact `tests/golden/baseline_2026-08-12.json`: UNCHANGED byte-for-byte (sha256: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`); `git diff` on golden artifact EMPTY
- Scan output verified: 310 scanned / 30 qualified / 15 ACTION; all required decision fields (status, entry, stop, target, shares, sector, rs, vcp, pf) present in all 30 qualified rows
- Backward compatibility: VERIFIED programmatically — `RSAnalyzer.get_raw_score`, `RSAnalyzer.assign_percentiles`, `VCPAnalyzer.calculate`, `StrategyValidator.run`, `DataEngine.get_data`, `DataEngine.get_current_price`, `config.TICKERS` (310), `config.CONFIG` all functional; `Strategy` identity identical via `engines.analysis` and `engines.strategies`; all 3 strategies importable
- No production files modified in this slice (documentation-only)
- Pre-regression backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase3_5-pre-regression.tar.gz` (verified, 6.6MB, 464 files)
- Final checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase3_5-checkpoint.tar.gz` (verified)
- Known issues: None
- Next step: STOP — await authorization for Slice 3.6 (Documentation + closeout)

**✅ SLICE 3.4 COMPLETE — MinerviniTrendTemplate** (2026-08-12, verified 2026-08-13):
- Objective: Implement `MinerviniTrendTemplate` as an additive, opt-in Strategy implementing the Strategy ABC — ACHIEVED
- New files:
  - `engines/strategies/minervini_template.py` — `MinerviniTrendTemplate(Strategy)` implementing `calculate(df, rs_rating=None)` / `get_score()` / `get_signals()` / `get_entry_stop_target()` + `is_actionable()`; 9-point canonical trend template (price vs MA150/MA200, MA150>MA200, MA200 uptrend ≥21 bars, MA50>MA150/MA200, price vs MA50, ≥30% above 52-week low, within 25% of 52-week high, RS rating ≥70 when supplied); trailing-only computations (look-ahead-free); min_data_bars 252; insufficient data → score 0, signals [], (0,0,0), actionable False
- Modified files:
  - `engines/strategies/__init__.py` — re-exports `MinerviniTrendTemplate` (backward compatible)
  - `tests/test_analysis.py` — added 11 new tests (importability, Strategy ABC compliance, qualifying uptrend, non-qualifying downtrend, 52-week bounds, RS criterion optional/assessed, entry/stop/target exactness, insufficient data, determinism, no input mutation, backward compatibility)
- Scoring: `score` = passed criteria / assessed total (0-8 without rs_rating; 0-9 with); `is_actionable()` = all assessed criteria pass; strategy score never fed into sentinel.py
- Backward compatibility: VERIFIED — VCPIndicator, VCPAnalyzer.calculate, StrategyValidator.run, RSIndicator, RSAnalyzer, RelativeStrengthRanking, VCPBreakoutStrategy, sentinel.py, config.yaml all unchanged
- Tests: full suite `pytest --tb=short` → **169 passed** (198s); `pytest tests/test_analysis.py --tb=short` → **116 passed** (8.1s); `pytest tests/test_analysis.py -k minervini` → **11 passed**; `pytest tests/test_regression.py -v --tb=short` → **9/9 passed** (153s)
- Golden artifact: UNCHANGED byte-for-byte (sha256: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`)
- 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- config.yaml: NOT modified; sentinel.py: NOT modified; golden baseline: NOT modified; engines/analysis.py: NOT modified
- Pre-implementation backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase3_4.tar.gz` (verified, 6.6MB, 463 files)
- Known issues: None
- Next step: STOP — report state, request authorization to commit

**✅ SLICE 3.3 COMPLETE — VCPBreakoutStrategy** (2026-08-12, verified 2026-08-13):
- Objective: Implement `VCPBreakoutStrategy` composing the existing `VCPIndicator` (no duplicated VCP detection logic), additive and opt-in — ACHIEVED
- New files:
  - `engines/strategies/vcp_breakout.py` — `VCPBreakoutStrategy(Strategy)` implementing `calculate(df)` / `get_score()` / `get_signals()` / `get_entry_stop_target()` + `is_actionable()`; composes `VCPIndicator(use_contraction_pivot=True)`; look-ahead-free; insufficient data (<130 bars) → score 0, signals [], entry/stop/target (0.0,0.0,0.0), actionable False
- Modified files:
  - `engines/strategies/__init__.py` — re-exports `VCPBreakoutStrategy` (backward compatible)
  - `tests/test_analysis.py` — added 10 new tests (importability, Strategy ABC compliance, confirmed breakout, volume requirement, failed breakout, entry/stop/target exactness, insufficient data, determinism, no input mutation, backward compatibility)
- Strategy semantics: confirmed breakout = close > pivot AND volume surge (ratio ≥ 1.2); entry = round(pivot*1.002, 2); stop = round(entry − atr*2.0, 2); target = round(entry + (entry−stop)*2.5, 2); failed breakout → score 0, signal "Breakout Failed"; score is the strategy's own scale (clamped 0-120), never fed into sentinel.py
- Backward compatibility: VERIFIED — `VCPIndicator`, `VCPAnalyzer.calculate`, `StrategyValidator.run`, `RSIndicator`, `RSAnalyzer`, `RelativeStrengthRanking`, `sentinel.py`, `config.yaml` all unchanged
- Tests: full suite `pytest --tb=short` → **158 passed** (164s); `pytest tests/test_analysis.py --tb=short` → **105 passed** (7.7s); `pytest tests/test_analysis.py -k vcpbreakout` → **10 passed**; `pytest tests/test_regression.py -v --tb=short` → **9/9 passed** (155s)
- Golden artifact: UNCHANGED byte-for-byte (sha256: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`)
- 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- config.yaml: NOT modified; sentinel.py: NOT modified; golden baseline: NOT modified
- Pre-implementation backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase3_3.tar.gz` (verified, 6.6MB, 462 files)
- Known issues: None
- Next step: STOP — report state, request authorization to commit

**✅ SLICE 3.2 COMPLETE — RelativeStrengthRanking Indicator** (2026-08-12, verified 2026-08-13):
- Objective: Implement `RelativeStrengthRanking` as an additive, opt-in INDICATOR (not a replacement for RSIndicator) — ACHIEVED
- New files:
  - `engines/strategies/rs_ranking.py` — `RelativeStrengthRanking` class (weighted-momentum raw RS vs optional benchmark, cross-sectional percentiles 1-99, `rank_universe` workflow)
- Modified files:
  - `engines/strategies/__init__.py` — re-exports `RelativeStrengthRanking` (backward compatible)
  - `tests/test_analysis.py` — added 11 new tests (importability, construction default/custom, deterministic calc, benchmark handling, ranking behavior, insufficient data, invalid-input validation, no DataFrame mutation, RSAnalyzer compatibility)
- Semantics: same windows/weights/percentile algorithm as `RSIndicator`; `compute_raw(df, benchmark_df=None)` subtracts benchmark weighted-momentum when supplied; returns `ERROR_SENTINEL` (-999.0) on insufficient data; `compute_percentiles`/`rank_universe` sort-as-you-go 1-99 ratings
- Backward compatibility: VERIFIED — `RSAnalyzer.get_raw_score`, `RSAnalyzer.assign_percentiles`, `VCPAnalyzer.calculate`, `StrategyValidator.run`, `DataEngine.get_data`, `DataEngine.get_current_price`, `config.TICKERS`, `config.CONFIG` all unchanged; `RSIndicator` untouched
- Tests: full suite `pytest --tb=short` → **148 passed** (156s); `pytest tests/test_analysis.py --tb=short` → **95 passed** (7.1s); `pytest tests/test_analysis.py -k rsranking` → **11 passed**; `pytest tests/test_regression.py -v --tb=short` → **9/9 passed** (147s)
- Golden artifact: UNCHANGED byte-for-byte (sha256: `1bf2f37ab3b7d13c707f53457d433bda95338c1b476dd1ff60fe00963527b397`)
- 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- config.yaml: NOT modified; sentinel.py: NOT modified; golden baseline: NOT modified
- Recovery checkpoint: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase3_3-2-recovery.tar.gz` (verified, 6.6MB, 462 files)
- Known issues: None
- Next step: STOP — report state, request authorization to commit

**✅ SLICE 3.1 COMPLETE — Strategy Package Structure** (2026-08-12):
- Objective: Establish `engines.strategies` package as home for Phase 3 strategies, with canonical Strategy ABC — ACHIEVED
- New files:
  - `engines/strategies/__init__.py` — package init, re-exports Strategy
  - `engines/strategies/base.py` — canonical Strategy ABC (moved from engines/analysis.py)
- Modified files:
  - `engines/analysis.py` — Strategy class replaced with `from engines.strategies.base import Strategy` (backward-compatible re-export)
  - `tests/test_analysis.py` — added 5 new tests for package structure
- Backward compatibility: VERIFIED — `from engines.analysis import Strategy` still works; `Strategy` is the same class via all import paths
- Tests: full suite `pytest --tb=short` → **137 passed** (167s); `pytest tests/test_analysis.py --tb=short` → **84 passed** (7.5s); `pytest tests/test_regression.py -v --tb=short` → **9/9 passed** (153s)
- Golden artifact: UNCHANGED byte-for-byte (sha256: `1bf2f37...`)
- Pre-phase backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_pre-phase3.tar.gz` (verified, 95KB, 41 files)
- Checkpoint backup: `~/ProjectBackups/US-stocks/US-stocks_2026-08-12_phase3_3-1-checkpoint.tar.gz` (verified, 96KB, 44 files)
- Known issues: None
- Next step: STOP — Slice 3.4 done; await authorization for Slice 3.5 (Regression/test gate)

**✅ MILESTONE 2.4.2C COMPLETE — UniverseManager** (continuation of in-progress Phase 2.4.2):
- Status: 2.4.2A (Strategy base class) and 2.4.2B (MarketDataProvider + DataEngineAdapter + CacheManager) are in the working tree (unchanged from pre-existing state); 2.4.2C implemented now
- Objective: Build UniverseManager (load, validate, filter delisted) as an opt-in class without changing any existing behavior — ACHIEVED
- Files changed (2.4.2C):
  - `config.py` — added `UniverseManager` class (built-in universe load, ticker validation/normalization, delisted filtering, external universe-file support, deterministic ordering; `from_config()` factory; `load()`/`tickers`/`__len__`/`__iter__`). Existing `config.TICKERS` computation untouched — callers unaffected
  - `tests/test_config.py` — added 15 new UniverseManager tests (importability, construction, from_config, load-matches-current-universe, deterministic ordering, validate, delisted filtering on/off, custom delisted set, custom base tickers, external file incl. order-preserved/comment-skipping, missing/empty file fallback)
- Architecture changes:
  - `UniverseManager` faithfully re-implements the existing `config.TICKERS` logic: built-in dedupe+sort → delisted filter → optional external universe file (file order preserved; blank/`#` lines skipped; unreadable/empty falls back to built-in)
  - Reads `data.filter_delisted` and `data.universe_file` from config.yaml (`sentinel/config.py`) with constructor overrides — config.yaml schema UNCHANGED
  - Opt-in: `config.TICKERS` remains the live source used by sentinel.py; the manager is additive
- Backward compatibility: VERIFIED — `UniverseManager().load() == config.TICKERS` (310 active tickers, sorted, unique, delisted absent)
- Tests: **110 passed** (23 config + 57 analysis + 18 fmp + 3 imports + 9 regression), full suite green (~93s + regression run)
- Regression: **9/9 executed and passed** — golden replay reproduces Phase 2.1 baseline exactly (310 scanned / 30 qualified / 15 ACTION)
- Golden artifact `tests/golden/baseline_2026-08-12.json`: UNCHANGED byte-for-byte
- Known issues: None
- Backup state: `US-stocks_2026-08-12_pre-phase2_4.tar.gz` and `US-stocks_2026-08-12_phase2_4-checkpoint.tar.gz` both intact (untouched)
- Next step: STOP — report to user (awaiting authorization for 2.4.2D)

**✅ MILESTONE 2.4.2D COMPLETE — VCP Pivot + Breakout Confirmation** (2026-08-12):
- Objective: Replace the naive 50-day-high pivot (`high.iloc[-50:].max()`) with a proper VCP contraction pivot and add breakout confirmation — ACHIEVED behind an explicit opt-in flag, so historical scan decisions are unchanged
- Files changed (2.4.2D):
  - `engines/analysis.py` — `VCPIndicator` gains opt-in `use_contraction_pivot` (+ `pivot_base_lookback`, `breakout_volume_ratio` constructor params, all constructor-only; config.yaml schema UNCHANGED). New public `detect_pivot(df, bar_idx=None)`; `calculate()` uses the proper pivot for the pivot bonus and adds a `pivot` key ONLY when the flag is enabled
  - `tests/test_analysis.py` — added 12 new tests (default legacy preservation, left-side pivot detection, handle structure/contraction, wide-handle negative, breakout confirmed, volume-required, failed breakout, insufficient data, no-look-ahead invariance, output schema, constructor validation, backward compat)
- Exact pivot algorithm: pivot = highest high of the LEFT side of the contraction base = max high over `[n-base_lookback, n-tightness_periods[0])` bars (base_lookback default 100, handle = last `tightness_periods[0]` = 20 bars); pivot_idx is the bar of that peak. Handle = last 20 bars (high/low/range_pct vs left_range_pct, `contracted` flag). Deterministic, uses only data ≤ evaluated bar
- Exact breakout logic: at evaluated bar, `close_above_pivot` = close > pivot; `volume_ratio` = short volume window (last `volume_lookback_short`) / long window (prior `volume_lookback_long`, gap-separated — same windows as VCP volume logic); `volume_surge` = ratio ≥ `breakout_volume_ratio` (default 1.2); `confirmed` = close_above_pivot AND volume_surge; `failed` = close below pivot AND handle high pierced it; signal ∈ {Breakout Confirmed, Breakout Failed, Awaiting Breakout}
- Configuration impact: NONE — config.yaml, sentinel.config schema, sentinel.py untouched. New knobs are constructor-only (opt-in). Default `VCPIndicator()`/`VCPAnalyzer.calculate()` output is byte-identical to before
- Look-ahead bias: VERIFIED free — `detect_pivot(df, bar_idx=i) == detect_pivot(df.iloc[:i+1])` for i ∈ {129,140,160,180,199}; all series sliced to the evaluated bar; `breakout.bar_index` = evaluated bar; `lookahead_free=True`
- Tests: **122 passed** (23 config + 70 analysis [incl. 13× RS/VCP legacy + 12 new pivot] + 18 fmp + 3 imports + 9 regression), full suite green (~6m17s, machine slow)
- Regression: **9/9 executed and passed** — golden replay reproduces Phase 2.1 baseline exactly (310 scanned / 30 qualified / 15 ACTION); default behavior unchanged
- Golden artifact `tests/golden/baseline_2026-08-12.json`: UNCHANGED byte-for-byte
- Unrelated files: `config.py`, `engines/data.py`, `tests/test_config.py` carry only their pre-existing 2.4.2B/C uncommitted state (untouched this slice)
- Known issues: None
- Backup/checkpoint: NEW `US-stocks_2026-08-12_phase2_4-2d-checkpoint.tar.gz` (verified, 4 files); existing `pre-phase2_4` and `phase2_4-checkpoint` backups untouched
- Next step: STOP — report to user (awaiting authorization for 2.4.2E)

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

### Short-term (Phase 2-3) ✅ COMPLETE
- [x] Refactor RSAnalyzer → RSIndicator (configurable windows/weights) — DONE 2026-08-12, backward compatible
- [x] Refactor VCPAnalyzer → VCPIndicator (proper pivot/handle detection) — DONE 2026-08-12 (Phase 2.3 + 2.4.2D)
- [x] Create MarketDataProvider abstraction (yfinance, FMP providers) — DONE 2026-08-12 (Phase 2.4.2B)
- [x] Implement CacheManager with compression — DONE 2026-08-12 (Phase 2.4.2B)
- [x] Build UniverseManager (load, validate, filter delisted) — DONE 2026-08-12, opt-in, backward compatible
- [x] Create Strategy abstract base class — DONE 2026-08-12 (Phase 2.4.2A)
- [x] VCP contraction pivot + breakout confirmation — DONE 2026-08-12 (Phase 2.4.2D)
- [x] StrategyValidator walk-forward (point-in-time) — DONE 2026-08-12 (Phase 2.4.2E)
- [x] Phase 2 regression gate — DONE 2026-08-12 (Phase 2.4.3 + 2.5)

### Medium-term (Phase 3-7)
- [x] Implement VCPBreakoutStrategy with breakout confirmation — DONE 2026-08-12 (Phase 3.3, uncommitted)
- [x] Implement MinerviniTrendTemplate (8 criteria) — DONE 2026-08-12 (Phase 3.4, uncommitted)
- [x] Implement RelativeStrengthRanking (vs SPY/sector) — DONE 2026-08-12 (Phase 3.2, uncommitted)
- [x] BacktestEngine with walk-forward validation — DONE 2026-08-14 (Phase 5.1, engines/backtest.py, committed `dc1c775`)
- [x] Purged k-fold CV on BacktestEngine (purge gap + embargo) — DONE 2026-08-14 (Phase 5.2, engines/backtest.py, committed `b11d9c3`)
- [x] Out-of-sample validation (train/validation/test split) — DONE 2026-08-14 (Phase 5.3, engines/backtest.py, uncommitted)
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
- **Available tests**: 137 (tests/test_config.py [23], tests/test_fmp.py [18], tests/test_analysis.py [84], tests/test_imports.py [3], tests/test_regression.py [9])
- **Last test run**: 2026-08-12 — `python -m pytest` → **137 passed** (incl. Phase 2.1 regression suite + Phase 2.2/2.3 indicator tests + Phase 2.4.2 A/B/C/D/E classes + Phase 3.1 strategy package tests)
- **Network**: fully mocked (test_fmp.py stubs requests.get; no live API calls in tests). Phase 2.1 regression replay is fully offline — it reads frozen OHLCV pickles and stubs fundamentals/news/insider (never hits yfinance/FMP).
- **Phase 2.1 regression suite** (tests/test_regression.py): replays the 310-ticker scan against a frozen snapshot (stored OUTSIDE repo under ~/ProjectBackups/US-stocks/frozen_snapshots/). Asserts (a) a fresh run reproduces the golden artifact exactly, (b) two runs are identical (determinism), (c) frozen replay matches the live 2026-08-12 reference on decision fields (310 scanned / 30 qualified / 15 ACTION), (d) golden has no secrets + correct baseline counts. Skips cleanly if the snapshot dir is absent; recreate via `./venv/bin/python scripts/capture_frozen_snapshot.py`.
- **RSIndicator tests** (tests/test_analysis.py, 17): config loading, validation, compute_raw (short/up/down/fallback), compute_percentiles (ascending/empty), NaN propagation, None handling, classmethod equivalence, backward compat with RSAnalyzer
- **VCPIndicator tests** (tests/test_analysis.py, 12): config loading, constructor overrides, validation (tightness_periods, ma_periods, pivot thresholds), calculate output format, edge cases (short frame, None), backward compat with VCPAnalyzer
- **VCP pivot/breakout tests** (tests/test_analysis.py, 12): left-side pivot detection, handle structure/contraction, breakout confirmed, volume-required, failed breakout, insufficient data, no-look-ahead, output schema, constructor validation, backward compat
- **Walk-forward tests** (tests/test_analysis.py, 9): API compat, output structure, deterministic, insufficient data, ATR isolation, point-in-time isolation, no-future-bar leakage, lookahead detection, legacy match
- **Strategy package tests** (tests/test_analysis.py, 5): package importable, importable from base, re-exported from init, same class via both paths, abstract direct instantiation fails
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
- **Pre-Phase 2.2 checkpoint (2026-08-12_04-15)**: US-stocks_2026-08-12_pre-phase2_2.tar.gz (verified, 43 files; created before RSIndicator refactor)
- **Separate resource**: frozen_snapshots/ at ~/ProjectBackups/US-stocks/ holds the 310-ticker frozen OHLCV snapshot (~13MB pickles + sectors + meta) — intentionally OUTSIDE the repo and EXCLUDED from tarball backups (regenerated from the project when needed)
- **Next backup**: At Phase 2.3 (VCP refactor) or Phase 2 completion

## 18. Next Step

**Phase 1 COMPLETE (2026-08-12). Security incident CLOSED. Phase 1 PUSHED to fork. Phase 2.1 (reproducibility gate) COMPLETE. Phase 2.2 MILESTONE 2.2.2 CHECKPOINT APPROVED.**
1. ✅ Credential rotated; ✅ new key in `.env` (600, ignored); ✅ history rewritten (credential purged, HEAD `0948a74`); ✅ pushed to fork `nomadintheuae-code/US-stocks` (force-with-lease, verified).
2. ✅ FMP news HTTP 402 isolated (FMPPlanError; app.py graceful notice).
3. ✅ Tests added (40 passing), requirements pinned, README rewritten, docs updated.
4. ✅ Phase 1 committed (`4617c29`, `40a2cc8`) and **PUSHED** to fork (normal fast-forward `0948a74..40a2cc8`, no force; verified origin/main == local HEAD).
5. ✅ Phase 1 final checkpoint backup created (00-55, verified).
6. ✅ **Phase 2.1 reproducibility gate** (2026-08-12): frozen snapshot at HEAD `b5b0986` → `~/ProjectBackups/US-stocks/frozen_snapshots/2026-08-12_b5b0986/` (310/310 pickles + sectors + meta); replay harness reproduces live decisions EXACTLY (310/30/15 ACTION, decision fields MATCH); golden artifact `tests/golden/baseline_2026-08-12.json`; 9 regression tests; full suite **49 passed**; pre-Phase 2.1 backup verified (`02-12_pre-phase2_1.tar.gz`).
7. ✅ **Phase 2.2 MILESTONE 2.2.2 CHECKPOINT APPROVED** (2026-08-12): `RSIndicator` class added to `engines/analysis.py` with configurable windows/weights, validation, and backward-compat classmethods; `RSAnalyzer` preserved as a thin wrapper. 17 new tests added. Full suite **66 passed**. 9/9 regression/golden tests pass. Backward compatibility verified. Pre-Phase 2.2 backup: `US-stocks_2026-08-12_pre-phase2_2.tar.gz`. Checkpoint backup: `US-stocks_2026-08-12_phase2_2-checkpoint.tar.gz`.

**Next milestone**: MILESTONE 2.2.3 (Regression — already passing) → 2.2.4 (Documentation) → 2.2.5 (Final verification) → STOP. Remaining Phase 2.2 milestones are verification/documentation only — no new implementation.

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

### 2026-08-12 — PHASE 2.4.2D VCP Pivot + Breakout Confirmation (engines/analysis.py)
**Goal**: Replace the naive 50-day-high VCP pivot with a proper contraction pivot and add breakout confirmation, without changing historical scan decisions.
**Work completed**:
- Verified the golden gate: default `VCPIndicator().calculate()` output flows into sentinel.py's `vcp` decision field — any default change would break the 310/30/15 baseline
- Implemented opt-in `use_contraction_pivot` (constructor-only) in `VCPIndicator`; `detect_pivot(df, bar_idx=None)` computes the left-side base high (base_lookback=100, handle = last 20 bars), handle metrics, and breakout state (close>pivot AND volume_ratio ≥ 1.2)
- `calculate()` uses the proper pivot for the pivot bonus and adds a `pivot` key ONLY when the flag is enabled; default path byte-identical (verified: analyzer == default indicator)
- Look-ahead avoidance: all series sliced to the evaluated bar; verified `detect_pivot(df, bar_idx=i) == detect_pivot(df.iloc[:i+1])` at multiple bars
- Added 12 tests (`tests/test_analysis.py`) covering left-side pivot, handle/contraction, breakout confirmed, volume-required, failed breakout, insufficient data, no-look-ahead, schema, validation, backward compat
**Tests**: full suite `venv/bin/python -m pytest --tb=short` → **122 passed** (~6m17s, machine slow); `pytest tests/test_regression.py -v` → **9/9 passed** (~5m52s)
**Results**: golden byte-for-byte unchanged; regression 9/9; config.yaml, sentinel.py, RSIndicator, UniverseManager, MarketDataProvider, CacheManager untouched; git diff --check CLEAN
**Problems**: full-suite/regression runs far slower than prior sessions (machine load/thermals); neither timed out after raising timeouts and both passed cleanly
**Decisions**: Implemented via explicit opt-in (no config schema change, no forced baseline change); constructor-only knobs; default behavior preserved; golden NOT modified
**Backup**: NEW checkpoint `US-stocks_2026-08-12_phase2_4-2d-checkpoint.tar.gz` (verified); pre-phase2_4 and phase2_4-checkpoint backups untouched
**Next step**: STOP — await authorization before 2.4.2E

### 2026-08-12 — PHASE 2.4.2E StrategyValidator Walk-Forward (engines/analysis.py)
**Goal**: Refactor StrategyValidator so walk-forward evaluation is point-in-time and does not use future bars, while preserving existing behavior for legacy callers.
**Work completed**:
- Inspected existing StrategyValidator: `run()` uses `high.iloc[i-20:i].max()` for pivot (correct: `i-20:i` excludes bar i) and `close.rolling(50).mean().iloc[i]` for MA50 (correct: rolling mean at bar i uses only bars ≤ i). ATR uses full-frame rolling (potential issue but `start = max(50, len(df)-250)` limits exposure)
- Implemented `_point_in_time_indicators(df, bar_idx)`: truncates frame to `df.iloc[:bar_idx+1]`, computes ATR(14)/MA50/pivot from truncated data only — structural look-ahead guard
- Implemented `evaluate_walk_forward(df, min_bars_for_entry=200, lookback_bars=250)`: point-in-time backtest using `_point_in_time_indicators()` for entry decisions; returns {profit_factor, trades, start, evaluated_bars}
- Implemented `run_walk_forward(df, ...)`: convenience wrapper returning float profit_factor
- Legacy `run()` preserved byte-for-byte unchanged — sentinel.py/app2.py production path unaffected
- Added 9 tests: API compat, output structure, deterministic, insufficient data, ATR isolation, point-in-time isolation, no-future-bar leakage, lookahead detection (synthetic spike frame), legacy match
**Tests**: `pytest tests/test_analysis.py --tb=short` → **79 passed** (13s); full suite `pytest --tb=short` → **132 passed** (366s); `pytest tests/test_regression.py -v` → **9/9 passed** (218s)
**Results**: golden byte-for-byte unchanged; regression 9/9; walk-forward tests all green; no future-bar leakage confirmed; legacy run() identical on normal data
**Problems**: None
**Decisions**: Opt-in walk-forward via separate methods (run_walk_forward/evaluate_walk_forward); legacy run() untouched; _point_in_time_indicators is the structural guarantee; config.yaml untouched; golden NOT modified
**Backup**: NEW checkpoint `US-stocks_2026-08-12_phase2_4-2e-checkpoint.tar.gz` (verified, 93KB, 41 files); previous backups untouched
**Next step**: STOP — Phase 2.4.2 complete (A through E); await authorization for Phase 2.4.3 regression

### 2026-08-12 — PHASE 2.4.3 Regression Gate (verification only)
**Goal**: Verify all Phase 2.4.2 changes produce no regressions against the Phase 2.1 golden baseline.
**Work completed**:
- Verified Phase 2.4.2E checkpoint backup intact: `US-stocks_2026-08-12_phase2_4-2e-checkpoint.tar.gz` (93KB, 41 files)
- Ran regression gate: `pytest tests/test_regression.py -v --tb=short` → **9/9 passed** (159s)
- Ran full suite: `pytest --tb=short` → **132 passed** (179s)
- Verified golden artifact `tests/golden/baseline_2026-08-12.json` UNCHANGED byte-for-byte (sha256: `1bf2f37...`)
- Verified 310 scanned / 30 qualified / 15 ACTION — bit-identical to golden baseline
- Verified decision fields match: status, entry, stop, target, shares, sector, rs, vcp, pf all identical
- Verified config.yaml NOT modified; golden baseline NOT modified
- Created Phase 2.4.3 checkpoint backup: `US-stocks_2026-08-12_phase2_4-3-regression-gate.tar.gz` (verified, 93KB, 41 files)
**Tests**: 132 passed, 0 failed, 0 skipped
**Results**: All Phase 2.4.2 changes verified regression-free; Phase 2.4 COMPLETE
**Problems**: None
**Decisions**: No code changes required — regression gate is verification-only
**Backup**: `US-stocks_2026-08-12_phase2_4-3-regression-gate.tar.gz` (verified); all previous backups untouched
**Next step**: STOP — Phase 2.4 COMPLETE; await authorization for Phase 2.5 or next work

### 2026-08-12 — PHASE 2.4.2C UniverseManager (config.py)
**Goal**: Implement UniverseManager (load, validate, filter the ticker universe) as an opt-in class preserving the current 310-ticker behavior.
**Work completed**:
- Inspected existing universe handling: `config.py` computes `TICKERS` from `_ORIGINAL`+`_EXPANSION` (dedupe+sort → delisted filter via `data.filter_delisted` → optional external `data.universe_file`), validated by sentinel/config.py `DataConfig`
- Implemented `UniverseManager` in `config.py`: `__init__(tickers=, delisted=, filter_delisted=, universe_file=)`, `from_config()`, `validate()` (uppercase/strip/dedupe/sort), `filter_delisted_tickers()`, `load()` (identical semantics to `config.TICKERS`), `tickers` property, `__len__`/`__iter__`
- Existing `config.TICKERS` left untouched — manager is opt-in; all callers (sentinel.py, engines, tests) unaffected
- Added 15 UniverseManager tests to `tests/test_config.py` (importability, construction, from_config, load-matches-current-universe == 310, deterministic ordering, validate, delisted on/off, custom delisted set, custom base tickers, external file + order/comment handling, missing/empty file fallback)
**Tests**: focused `pytest tests/test_config.py` → 23 passed; full suite `venv/bin/python -m pytest --tb=short` → **110 passed**; `pytest tests/test_regression.py` → **9/9 passed (executed, not skipped)**
**Results**: `UniverseManager().load() == config.TICKERS` verified (310 active, sorted, unique, no delisted); golden artifact byte-identical; config.yaml and sentinel.py untouched
**Problems**: Two new tests initially omitted the `tmp_path` fixture arg (NameError) — fixed by adding the parameter; then all green
**Decisions**: UniverseManager placed in config.py (natural home of the universe logic, no new architecture); opt-in only; external-file semantics preserved exactly (replace, file order, silent fallback)
**Backup**: pre-existing `US-stocks_2026-08-12_pre-phase2_4.tar.gz` + `US-stocks_2026-08-12_phase2_4-checkpoint.tar.gz` both intact (not overwritten)
**Next step**: STOP — await authorization before 2.4.2D

### 2026-08-12 04:15 — PHASE 2.2 RSIndicator REFACTOR (engines/analysis.py)
**Goal**: Refactor RSAnalyzer into a configurable RSIndicator without changing behavior.
**Work completed**:
- Discovery: mapped RSAnalyzer location (`engines/analysis.py:169-194`), callers (`sentinel.py:42,48`, `ecr_strategy.py:85`, `app2.py:100`), hardcoded magic numbers (252/126/63/21 windows, 0.4/0.2/0.2/0.2 weights, -999.0 sentinel), and confirmed config.yaml `rs:` section existed but was unused
- Implemented `RSIndicator` class: configurable `windows`/`weights`/`min_data_days` (defaults from config.yaml `rs:` section), validation (weights sum to 1.0, windows/weights length match), `compute_raw()` and `compute_percentiles()` instance methods, backward-compat `get_raw_score()` / `assign_percentiles()` classmethods
- `RSAnalyzer` preserved as thin static wrapper delegating to `RSIndicator` — zero behavioral change for all existing callers
- Added 17 new tests: config loading, custom config, validation errors, raw score (short/up/down/fallback), percentiles (ascending/empty), NaN propagation, None handling, classmethod equivalence, backward compat with RSAnalyzer
**Tests**: full suite `venv/bin/python -m pytest` → **66 passed** (49 original + 17 new), ~160s
**Results**: RSIndicator introduced, backward compatible, golden regression suite unaffected (all 9 regression tests pass)
**Problems**: Initial NaN test had incorrect expectation (original code returns NaN, not sentinel, for NaN close); fixed to match actual behavior
**Decisions**: NaN handling preserved as-is (no behavior change); RSAnalyzer kept as wrapper (not deprecated yet); config.yaml schema unchanged (rs: section already existed)
**Backup**: `US-stocks_2026-08-12_pre-phase2_2.tar.gz` (verified, 43 files)
**Next step**: MILESTONE 2.2.4 (Documentation finalization) → 2.2.5 (Final verification) → STOP/report

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