# USB Transfer Package - SENTINEL PRO

## 📦 What's Included

### Source Code
- `sentinel.py` — Main batch scanner
- `app.py` — Streamlit dashboard v1 (FMP)
- `app2.py` — Streamlit dashboard v2 (ECR)
- `engines/` — All engine modules
- `tests/` — Full test suite (555 tests)
- `scripts/` — Utility scripts
- `config.yaml` — Configuration (single source of truth)
- `requirements.txt` — Pinned dependencies

### AI Configuration
- `AI_INSTRUCTIONS.md` — Universal AI rules (677 lines)
- `AGENTS.md` — OpenAI Codex pointer
- `CLAUDE.md` — Claude Code pointer
- `.aider.conf.yml` — Aider config
- `hermes-skills.yaml` — Hermes skills

### Documentation
- `PROJECT_CONTEXT.md` — Full project state
- `README.md` — Project overview
- `AUDIT_REPORT.md` — Audit report

### Tests & Golden Baseline
- `tests/golden/baseline_2026-08-12.json` — Regression baseline
- `tests/regression_harness.py` — Frozen replay harness

---

## 🚫 NOT Included (Must Setup Manually)

### Secrets (NEVER in USB/git)
- `.env` — Contains API keys (FMP, DeepSeek, LINE, FRED, Alpha Vantage)

### Generated/Cache
- `venv/` — Python virtual environment
- `cache_v45/` — yfinance OHLCV cache
- `cache/` — FMP API cache
- `results/*.json` — Daily scan outputs
- `__pycache__/` — Python bytecode

---

## 🔧 Device Setup (Dubai Laptop)

### Step 1: Copy USB to Device
```bash
# Insert USB, then:
cp -r /media/USB/US-stocks ~/Projects/US-stocks
cd ~/Projects/US-stocks
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Copy .env (Manually & Securely)
```bash
# DO NOT copy .env via USB/git
# Manually create .env with your API keys:
cat > .env << 'EOF'
FMP_API_KEY=your_fmp_key_here
DEEPSEEK_API_KEY=your_deepseek_key_here
FRED_API_KEY=your_fred_key_here
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
LINE_CHANNEL_ACCESS_TOKEN=your_line_token_here
LINE_USER_ID=your_line_user_id_here
EOF

# Set permissions
chmod 600 .env
```

### Step 5: Install MCP Servers (for AI CLI tools)
```bash
# SEC EDGAR
pip install sec-edgar-mcp

# FRED (Federal Reserve Data)
pip install fred-mcp

# News feeds
pip install mcp-news

# financex + finance-data (via npx, auto-installed)
```

### Step 6: Verify Installation
```bash
./venv/bin/python -m pytest --tb=short -q
# Expected: 555 passed

./venv/bin/python -c "from engines.analysis import VCPAnalyzer; print('OK')"
# Expected: OK
```

### Step 7: Configure AI CLI Tools

#### Hermes Agent
```bash
pip install hermes-agent
hermes init
# Hermes reads hermes-skills.yaml automatically
```

#### OpenAI Codex
```bash
npm install -g @openai/codex
# Codex reads AGENTS.md automatically
```

#### Claude Code
```bash
npm install -g @anthropic-ai/claude-code
# Claude reads CLAUDE.md automatically
```

#### Aider
```bash
pip install aider-chat
# Aider reads .aider.conf.yml automatically
```

---

## 🔌 MCP Servers Required

### For Full AI Agent Functionality

| MCP Server | Purpose | Install | API Key |
|------------|---------|---------|---------|
| **sec-edgar** | SEC filings (10-K, 10-Q, 8-K, Form 4) | `pip install sec-edgar-mcp` | None (free) |
| **fred** | Federal Reserve data (GDP, inflation, rates) | `pip install fred-mcp` | `FRED_API_KEY` |
| **alpha-vantage** | Market data, technical indicators | Remote MCP | `ALPHA_VANTAGE_API_KEY` |
| **financex** | Financial analysis, options, DCF | `npx mcp-financex` | None |
| **finance-data** | Stock quotes, portfolio, crypto | `npx finance-mcp-server` | None |
| **news** | News feeds (1100+ RSS sources) | `pip install mcp-news` | None |
| **github** | Repository management | Remote MCP | GitHub auth |

### MCP Configuration File
Location: `~/.config/opencode/opencode.jsonc`

```json
{
  "mcp": {
    "sec-edgar": {
      "type": "local",
      "command": ["venv/bin/python", "-m", "sec_edgar_mcp.server"],
      "enabled": true,
      "environment": {
        "SEC_EDGAR_USER_AGENT": "SENTINEL-PRO/1.0 (https://github.com/nomadintheuae-code/US-stocks)"
      }
    },
    "fred": {
      "type": "local",
      "command": ["venv/bin/python", "-m", "fred_mcp.server"],
      "enabled": true,
      "environment": {
        "FRED_API_KEY": "{env:FRED_API_KEY}"
      }
    },
    "alpha-vantage": {
      "type": "remote",
      "url": "https://mcp.alphavantage.co/mcp?apikey={env:ALPHA_VANTAGE_API_KEY}",
      "enabled": true
    },
    "financex": {
      "type": "local",
      "command": ["npx", "-y", "mcp-financex"],
      "enabled": true
    },
    "finance-data": {
      "type": "local",
      "command": ["npx", "-y", "finance-mcp-server"],
      "enabled": true
    },
    "news": {
      "type": "local",
      "command": ["venv/bin/python", "-m", "mcp_news"],
      "enabled": true
    },
    "github": {
      "type": "remote",
      "url": "https://api.githubcopilot.com/mcp/",
      "enabled": true
    }
  }
}
```

---

## 📋 Complete Setup Checklist

- [ ] Copy USB to `~/Projects/US-stocks`
- [ ] Create venv: `python -m venv venv`
- [ ] Install deps: `pip install -r requirements.txt`
- [ ] Create `.env` with API keys (chmod 600)
- [ ] Install MCP servers (see table above)
- [ ] Copy `opencode.jsonc` to `~/.config/opencode/`
- [ ] Run tests: `./venv/bin/python -m pytest --tb=short -q`
- [ ] Verify imports: `python -c "from engines.analysis import VCPAnalyzer; print('OK')"`
- [ ] Configure AI CLI (Hermes/Codex/Claude/Aider)
- [ ] Test AI CLI reads instructions correctly

---

## 🔐 API Keys Needed

| Service | Key | Where to Get | Free? |
|---------|-----|--------------|-------|
| FMP | `FMP_API_KEY` | financialmodelingprep.com | Limited |
| DeepSeek | `DEEPSEEK_API_KEY` | platform.deepseek.com | Yes |
| FRED | `FRED_API_KEY` | fred.stlouisfed.org | Yes |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | alphavantage.co | Limited |
| LINE Notify | `LINE_CHANNEL_ACCESS_TOKEN` | notify-bot.line.me | Yes |

---

## 🔄 Sync Protocol

### After Working on Dubai Device
```bash
# On Dubai device
git add -A
git commit -m "dubai: description of changes"
git push origin main

# On CachyOS device
git pull origin main
```

### Files to Always Sync
- All `*.py` files
- `AI_INSTRUCTIONS.md`
- `PROJECT_CONTEXT.md`
- `config.yaml`
- `requirements.txt`
- `tests/`

### Files NEVER to Sync
- `.env` (secrets)
- `venv/` (recreate)
- `cache_v45/` (regenerate)
- `__pycache__/` (regenerate)

---

*Package created: 2026-08-20*
*Version: 1.1*
