"""Module import / startup smoke tests."""
import importlib

CORE_MODULES = [
    "config",
    "sentinel",
    "sentinel.config",
    "core_fmp",
    "engines.data",
    "engines.analysis",
    "engines.fundamental",
    "engines.news",
    "engines.notify",
    "engines.ecr_strategy",
    "engines.sentinel_efficiency",
    "engines.filters",
    "engines.backtest",
    "engines.earnings",
    "engines.patterns",
    "engines.regime",
    "engines.risk",
    "engines.pipeline",
]


def test_core_modules_import():
    for mod in CORE_MODULES:
        importlib.import_module(mod)


def test_streamlit_apps_import():
    # Streamlit bare-mode warnings are acceptable; must not raise.
    importlib.import_module("app2")


def test_all_tickers_are_upper():
    import config

    for t in config.TICKERS:
        assert t == t.upper()
