# AI INSTRUCTIONS

## Project Rules for SENTINEL PRO - US Stock Scanner

These rules are permanent and must be followed in all sessions.

---

## 1. Coding Rules

### General
- **Language**: Python 3.10+ (currently 3.14.6)
- **Style**: Follow existing code conventions in the project
- **Type hints**: Use type hints for all new functions
- **Docstrings**: Google/NumPy style for public functions/classes
- **No hardcoded values**: All thresholds, periods, weights must be configurable
- **No magic numbers**: Extract to config with descriptive names

### Architecture
- **Separation of concerns**: Data → Indicators → Strategies → Filters → Ranking → Output
- **Dependency inversion**: Strategies depend on Indicator interfaces, not implementations
- **Provider abstraction**: Swap yfinance/FMP/Alpaca without changing strategies
- **Universe agnostic**: Support US stocks, ETFs, Crypto, Forex via same pipeline
- **Cache-first**: All providers return cached data when fresh
- **Batch processing**: Vectorized operations where possible

### Error Handling
- Never use bare `except:` - catch specific exceptions
- Log errors with context (ticker, operation, error type)
- Return structured error results, not None/exceptions
- Fail gracefully - partial results better than total failure

### Security
- **NEVER** put API keys, passwords, tokens in source code
- **NEVER** commit .env files with secrets
- **NEVER** print secrets in logs
- Use environment variables or secure configuration
- Rotate keys if accidentally exposed

---

## 2. Testing Rules

- **Framework**: pytest
- **Coverage target**: >80% for indicators, strategies, core logic
- **Test types**:
  - Unit tests for each indicator (known inputs → expected outputs)
  - Integration tests for data pipeline
  - Property-based tests for mathematical functions
  - Regression tests for known bugs
- **Test data**: Use fixtures, synthetic data, or cached real data
- **No network calls in unit tests**: Mock all external APIs
- **Run tests before committing**: `pytest -xvs`
- **Test naming**: `test_<module>_<function>_<scenario>`

---

## 3. Git Rules

### Before Work
```bash
git status
git log -5 --oneline
```

### During Work
- Make small, focused commits
- Commit messages: conventional commits format
  - `feat: add VCP breakout confirmation`
  - `fix: remove look-ahead bias in backtest`
  - `refactor: extract RS indicator`
  - `config: externalize thresholds to yaml`
- No automatic commits without user approval

### After Work
```bash
git status
git diff
# Review changes before reporting
```

### Branching
- `main`: Stable, deployable
- Feature branches: `feature/<name>`, `fix/<name>`, `refactor/<name>`
- No force push to main

---

## 4. Backup Rules

### When to Backup (MANDATORY)
- Before major refactoring
- Before architecture changes
- Before dependency migrations
- Before large strategy changes
- Before deleting/moving files
- Before risky AI modifications
- When user says: "احفظ العمل", "احفظ المشروع", "أنهِ الجلسة", "Session End", "Save work"

### Backup Format
- **Format**: tar.gz
- **Location**: ~/ProjectBackups/US-stocks/
- **Filename**: US-stocks_YYYY-MM-DD_HH-MM.tar.gz
- **Contents**: Source code, tests, config templates, README, PROJECT_CONTEXT.md, AI_INSTRUCTIONS.md
- **Exclude**: venv, __pycache__, cache_v45/, cache/, results/*.json, .env, *.log

### Backup Verification (MANDATORY)
1. Verify file exists
2. Verify not empty/corrupted: `tar -tzf backup.tar.gz`
3. Verify important files present
4. Record in PROJECT_CONTEXT.md
5. **DO NOT claim success if verification fails**

### Retention
- Keep multiple recovery points
- Ask before deleting old backups
- Never assume newest backup is sufficient

---

## 5. Documentation Rules

### PROJECT_CONTEXT.md
- Update after EVERY significant change
- Must reflect CURRENT REAL STATE
- Include: Current State, Pending Tasks, Next Step, Session History
- Never fabricate information

### AI_INSTRUCTIONS.md
- Update only when permanent rules change
- Keep stable across sessions

### Code Documentation
- Update docstrings when changing function signatures
- Add comments for complex financial logic
- Document look-ahead bias prevention measures

### Session History Entry (required at session end)
```markdown
### YYYY-MM-DD HH:MM
Goal:
Work completed:
Files changed:
Tests:
Results:
Problems:
Decisions:
Backup:
Next step:
```

---

## 6. Performance Rules (Hardware Constraints)

**Target Hardware**: Intel i5-5350U, 4 cores, 8GB RAM, no GPU

### Mandatory
- **Max workers**: Configurable, default 2-3 (leave 1-2 for OS)
- **No aggressive multiprocessing**: Use ThreadPoolExecutor for I/O bound
- **No loading all data into RAM**: Stream/chunk processing
- **Lazy loading**: Load data only when needed
- **Caching**: Use disk cache with TTL, compress with zstd/lz4
- **Batch API calls**: yfinance supports multi-ticker download

### Before Heavy Operations
- Explain expected CPU/RAM impact
- Get user approval for operations >30s or >500MB RAM
- Monitor resources during execution

### Optimization Priorities
1. Reduce API calls (batching, caching)
2. Reduce RAM footprint (chunking, streaming)
3. Parallelize I/O (ThreadPoolExecutor)
4. Vectorize calculations (pandas/numpy)
5. Compress cache (zstd)

---

## 7. Financial Logic Rules

### Look-Ahead Bias Prevention
- **NEVER** use future data in signal generation
- Backtest must use walk-forward / purged k-fold
- Train/Validation/Test splits strictly enforced
- Signal at bar `t` can only use data up to bar `t`

### Survivorship Bias
- Universe must support historical snapshots
- Document current universe composition date
- Backtest on point-in-time universes when possible

### Data Adjustments
- Verify split/dividend adjustment (yfinance auto_adjust=True)
- Document adjustment method
- Test with known corporate actions

### VCP Definition
- Proper VCP pivot = contraction high (not 50-day high)
- Handle detection required (final shakeout before breakout)
- Volume dry-up must precede pivot, not overlap
- Breakout confirmation: volume surge + close above pivot

### RS Calculation
- Cross-sectional percentile within universe (current method OK)
- Optional: Relative to benchmark (SPY, sector ETF)
- Document weighting scheme and lookback periods

---

## 8. API Rules

### yfinance
- Respect rate limits (batch requests, cache aggressively)
- Handle delisted tickers gracefully
- Use `auto_adjust=True`, `repair=True`
- Timeout: 15s default, configurable

### FMP (Financial Modeling Prep)
- API key via environment variable ONLY
- Cache responses (12h-24h TTL)
- Handle rate limits (stable endpoints preferred)

### DeepSeek (AI Analysis)
- Optional feature, only if DEEPSEEK_API_KEY set
- Timeout: 30s
- Sanitize prompts (no PII, no secrets)

### LINE Notify
- Optional, only if tokens configured
- Message chunking (4000 char limit)
- Graceful degradation if unavailable

---

## 9. Configuration Rules

### Configuration Hierarchy
1. **config.yaml** - All tunable parameters (committed)
2. **.env** - Secrets and environment-specific values (NOT committed)
3. **Defaults in code** - Only as fallback, documented

### Config Structure (config.yaml)
```yaml
capital:
  jpy: 1000000
  max_positions: 20
  account_risk_pct: 0.015
  max_same_sector: 2

scan:
  min_rs_rating: 70
  min_vcp_score: 55
  min_profit_factor: 1.1

exit:
  stop_loss_atr: 2.0
  target_r_multiple: 2.5

cache:
  price_expiry_hours: 12
  fundamental_expiry_hours: 24
  news_expiry_hours: 1

vcp:
  tightness_periods: [20, 30, 40, 60]
  volume_lookback_short: 20
  volume_lookback_long: 60
  ma_periods: [50, 150, 200]

rs:
  windows: [252, 126, 63, 21]
  weights: [0.4, 0.2, 0.2, 0.2]

performance:
  max_workers: 3
  batch_size: 50
  cache_compression: "zstd"
```

### Validation
- Use Pydantic for config validation
- Fail fast on invalid config
- Document all parameters with descriptions

---

## 10. Session Protocol

### Session Start (MANDATORY)
1. Read AI_INSTRUCTIONS.md
2. Read PROJECT_CONTEXT.md
3. Read README.md
4. Check `git status`
5. Check `git log -5 --oneline`
6. Establish: Current state, Last completed task, Known problems, Current plan, Next step

### Session Workflow (for each task)
```
INSPECT → UNDERSTAND → PLAN → BACKUP → IMPLEMENT → TEST → REVIEW → DOCUMENT → VERIFY → SAVE
```

### Session End (when user says save/end)
1. Stop development
2. Run relevant tests
3. Check git status & diff
4. Check for untracked important files
5. Update PROJECT_CONTEXT.md
6. Update Session History
7. Update Next Step
8. Create external backup (if important changes)
9. Verify backup
10. Report: SESSION SAVED

---

## 11. Project Structure Rules

### Directory Layout
```
~/Projects/US-stocks/
├── PROJECT_CONTEXT.md
├── AI_INSTRUCTIONS.md
├── README.md
├── config.yaml
├── .env.sample
├── requirements.txt
├── pyproject.toml (optional)
├── src/
│   ├── sentinel/          # Main package
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── data/
│   │   ├── indicators/
│   │   ├── strategies/
│   │   ├── filters/
│   │   ├── ranking/
│   │   ├── backtest/
│   │   ├── output/
│   │   └── cli.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── scripts/               # Utility scripts
├── docs/                  # Additional documentation
└── notebooks/             # Exploration notebooks
```

### Current State (Technical Debt)
- Code currently in root directory (not in src/)
- Will be restructured during Phase 1-2 refactoring
- Do NOT break existing functionality during restructure

---

## 12. Prohibited Actions

- ❌ Rewrite entire project without approval
- ❌ Delete existing functionality without approval
- ❌ Commit secrets/API keys
- ❌ Use sudo without explicit approval
- ❌ Execute destructive system commands
- ❌ Skip backup before risky changes
- ❌ Claim completion if tests fail or app doesn't run
- ❌ Hardcode values that should be configurable
- ❌ Introduce architectural changes without justification
- ❌ Assume previous conversation is available (read files instead)

---

## 13. AI Handoff Requirements

The project must be transferable to ANY AI model (GPT, Claude, Gemini, Nemotron, etc.)

A new AI must be able to continue by reading ONLY:
1. AI_INSTRUCTIONS.md
2. PROJECT_CONTEXT.md
3. README.md
4. Git history
5. External backup

**If an important decision exists only in conversation: DOCUMENT IT in PROJECT_CONTEXT.md**

---

## 14. Definition of Done

A task is NOT complete until:
- ✅ Tests pass (or documented why not)
- ✅ Application runs without errors
- ✅ No important errors remain
- ✅ Backup created and verified (if applicable)
- ✅ Important changes documented in PROJECT_CONTEXT.md
- ✅ Implementation is complete (not partial)
- ✅ Session history updated

Report REAL status, not desired status.

---

## 15. Emergency Recovery

If session interrupted (crash, network, context limit, model change):
1. **DO NOT** assume previous conversation available
2. Recover using: AI_INSTRUCTIONS.md + PROJECT_CONTEXT.md + README.md + Git + External Backup
3. Determine current REAL state first
4. Never invent what happened in previous session
5. Resume from "Next Step" in PROJECT_CONTEXT.md

---

*Last updated: 2026-08-11*
*Version: 1.0*