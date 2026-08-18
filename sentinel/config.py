"""
Configuration management for SENTINEL PRO.
Loads from config.yaml and .env with Pydantic validation.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv


# Load .env file if exists
load_dotenv()


class CapitalConfig(BaseModel):
    jpy: int = Field(default=1_000_000, ge=0, description="運用資金（円）")
    max_positions: int = Field(default=20, ge=1, le=100, description="最大同時保有数")
    account_risk_pct: float = Field(default=0.015, gt=0, le=0.1, description="1トレードあたりリスク")
    max_same_sector: int = Field(default=2, ge=1, le=10, description="セクターあたり最大銘柄数")
    max_position_pct: float = Field(default=0.40, gt=0, le=1.0, description="1ポジション最大比率")


class ScanConfig(BaseModel):
    min_rs_rating: int = Field(default=70, ge=0, le=99, description="RS最低スコア（パーセンタイル）")
    min_vcp_score: int = Field(default=55, ge=0, le=105, description="VCP最低スコア")
    min_profit_factor: float = Field(default=1.1, gt=0, le=10.0, description="最低プロフィットファクター")


class ExitConfig(BaseModel):
    stop_loss_atr: float = Field(default=2.0, gt=0, le=10.0, description="損切りATR倍率")
    target_r_multiple: float = Field(default=2.5, gt=0, le=20.0, description="利確R倍率")


class VCPConfig(BaseModel):
    tightness_periods: List[int] = Field(default=[20, 30, 40, 60], description="収縮計算期間")
    volume_lookback_short: int = Field(default=20, ge=5, le=100, description="直近出来高期間")
    volume_lookback_long: int = Field(default=60, ge=20, le=200, description="比較対象出来高期間")
    volume_lookback_gap: int = Field(default=20, ge=0, le=50, description="期間ギャップ")
    ma_periods: List[int] = Field(default=[50, 150, 200], description="移動平均期間")
    pivot_near_pct: float = Field(default=0.04, gt=0, le=0.5, description="ピボット近接閾値(4%)")
    pivot_far_pct: float = Field(default=0.08, gt=0, le=0.5, description="ピボット遠隔閾値(8%)")
    max_tightness_score: int = Field(default=40, ge=0, le=50, description="最大収縮スコア")
    max_volume_score: int = Field(default=30, ge=0, le=40, description="最大出来高スコア")
    max_ma_score: int = Field(default=30, ge=0, le=40, description="最大MAスコア")
    max_pivot_bonus: int = Field(default=5, ge=0, le=10, description="最大ピボットボーナス")

    @field_validator("tightness_periods", "ma_periods")
    @classmethod
    def check_increasing(cls, v: List[int]) -> List[int]:
        if v != sorted(v):
            raise ValueError("Periods must be in increasing order")
        return v

    @field_validator("pivot_far_pct")
    @classmethod
    def check_pivot_thresholds(cls, v: float, info) -> float:
        if "pivot_near_pct" in info.data and v <= info.data["pivot_near_pct"]:
            raise ValueError("pivot_far_pct must be greater than pivot_near_pct")
        return v


class RSConfig(BaseModel):
    windows: List[int] = Field(default=[252, 126, 63, 21], description="ルックバック窓（営業日数）")
    weights: List[float] = Field(default=[0.4, 0.2, 0.2, 0.2], description="各窓の重み（合計1.0）")
    min_data_days: int = Field(default=21, ge=5, le=252, description="最低必要データ日数")

    @field_validator("weights")
    @classmethod
    def check_weights_sum(cls, v: List[float]) -> List[float]:
        if abs(sum(v) - 1.0) > 0.001:
            raise ValueError("RS weights must sum to 1.0")
        return v

    @field_validator("windows")
    @classmethod
    def check_windows_decreasing(cls, v: List[int]) -> List[int]:
        if v != sorted(v, reverse=True):
            raise ValueError("Windows must be in decreasing order (longest first)")
        return v

    @model_validator(mode="after")
    def check_windows_weights_match(self) -> "RSConfig":
        if len(self.windows) != len(self.weights):
            raise ValueError("Number of windows must match number of weights")
        return self


class BacktestConfig(BaseModel):
    lookback_bars: int = Field(default=250, ge=50, le=1000, description="バックテスト対象バー数")
    min_bars_for_entry: int = Field(default=50, ge=20, le=200, description="エントリー判定最小バー数")
    pivot_lookback: int = Field(default=20, ge=5, le=100, description="ピボット計算ルックバック")
    ma_filter_period: int = Field(default=50, ge=10, le=200, description="MAフィルター期間")


class SESConfig(BaseModel):
    period: int = Field(default=20, ge=5, le=100, description="計算期間")
    fe_thresholds: List[float] = Field(default=[0.60, 0.50, 0.40, 0.30], description="フラクタル効率閾値")
    fe_scores: List[int] = Field(default=[30, 25, 20, 10], description="フラクタル効率スコア")
    force_thresholds: List[float] = Field(default=[0.80, 0.65, 0.55], description="フォース指数閾値")
    force_scores: List[int] = Field(default=[30, 20, 10], description="フォース指数スコア")
    vol_contraction_thresholds: List[float] = Field(default=[0.50, 0.65, 0.80, 1.20], description="ボラティリティ収縮閾値")
    vol_contraction_scores: List[int] = Field(default=[20, 15, 10, -5], description="ボラティリティ収縮スコア")
    clv_thresholds: List[float] = Field(default=[0.60, 0.55, 0.50], description="CLV閾値")
    body_thresholds: List[float] = Field(default=[0.10, 0.00], description="ボディ閾値")
    bar_scores: List[int] = Field(default=[20, 15, 10], description="バー品質スコア")


class ECRConfig(BaseModel):
    vcp_weight: float = Field(default=0.4, gt=0, le=1, description="VCP重み")
    ses_weight: float = Field(default=0.3, gt=0, le=1, description="SES重み")
    rs_weight: float = Field(default=0.3, gt=0, le=1, description="RS重み")
    vcp_ses_bonus_high: float = Field(default=1.15, ge=1.0, le=2.0, description="高スコアボーナス")
    vcp_ses_bonus_mid: float = Field(default=1.05, ge=1.0, le=2.0, description="中スコアボーナス")
    ignition_rank_delta: int = Field(default=15, ge=0, le=100, description="点火ランク変化閾値")
    ignition_rank_slope: float = Field(default=3.0, ge=0, le=20.0, description="点火ランク傾斜閾値")
    ignition_vol_ratio: float = Field(default=1.8, ge=1.0, le=10.0, description="点火出来高比閾値")
    accumulation_rank: int = Field(default=80, ge=0, le=100, description="蓄積ランク閾値")
    accumulation_rank_slope: float = Field(default=2.0, ge=0, le=10.0, description="蓄積ランク傾斜閾値")
    accumulation_dist_max: float = Field(default=0.08, ge=0, le=0.5, description="蓄積距離最大")
    release_dist: float = Field(default=-0.07, ge=-1.0, le=0.0, description="放出距離閾値")
    release_rank_slope: float = Field(default=0.0, ge=-10.0, le=10.0, description="放出ランク傾斜閾値")

    @model_validator(mode="after")
    def check_weights_sum(self) -> "ECRConfig":
        total = self.vcp_weight + self.ses_weight + self.rs_weight
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"ECR weights must sum to 1.0, got {total}")
        return self


class CacheConfig(BaseModel):
    price_expiry_hours: int = Field(default=12, ge=1, le=168, description="価格キャッシュ期限(時間)")
    fundamental_expiry_hours: int = Field(default=24, ge=1, le=168, description="ファンダメンタルキャッシュ期限(時間)")
    news_expiry_hours: int = Field(default=1, ge=1, le=168, description="ニュースキャッシュ期限(時間)")
    insider_expiry_hours: int = Field(default=6, ge=1, le=168, description="インサイダーキャッシュ期限(時間)")
    sector_expiry_days: int = Field(default=30, ge=1, le=365, description="セクターキャッシュ期限(日)")
    compression: str = Field(default="zstd", description="圧縮方式")

    @field_validator("compression")
    @classmethod
    def check_compression(cls, v: str) -> str:
        allowed = ["zstd", "lz4", "gzip", "none"]
        if v not in allowed:
            raise ValueError(f"Compression must be one of {allowed}")
        return v


class PerformanceConfig(BaseModel):
    max_workers: int = Field(default=3, ge=1, le=8, description="最大ワーカー数")
    batch_size: int = Field(default=50, ge=10, le=200, description="バッチ取得サイズ")
    request_timeout: int = Field(default=15, ge=5, le=60, description="リクエストタイムアウト(秒)")
    rate_limit_delay: float = Field(default=0.1, ge=0, le=5.0, description="API呼び出し間遅延(秒)")


class DataConfig(BaseModel):
    default_period: str = Field(default="700d", description="デフォルト取得期間")
    min_bars_required: int = Field(default=150, ge=50, le=500, description="最低必要バー数")
    auto_adjust: bool = Field(default=True, description="分割・配当調整")
    repair: bool = Field(default=True, description="データ修復")
    universe_file: str = Field(default="", description="外部ユニバースファイル")
    filter_delisted: bool = Field(default=True, description="上場廃止銘柄除外")


class LiquidityFilterConfig(BaseModel):
    min_avg_dollar_volume: Optional[float] = Field(default=None, ge=0, description="最低平均出来高(USD/日)")
    min_avg_volume: Optional[float] = Field(default=None, ge=0, description="最低平均出来高(株/日)")


class MarketCapFilterConfig(BaseModel):
    min_usd: Optional[float] = Field(default=None, ge=0, description="最低時価総額(USD)")
    max_usd: Optional[float] = Field(default=None, ge=0, description="最高時価総額(USD)")

    @model_validator(mode="after")
    def check_range(self) -> "MarketCapFilterConfig":
        if self.min_usd is not None and self.max_usd is not None and self.min_usd > self.max_usd:
            raise ValueError("market_cap.min_usd must be <= market_cap.max_usd")
        return self


class SectorFilterConfig(BaseModel):
    include: List[str] = Field(default_factory=list, description="許可セクター（空なら全て）")
    exclude: List[str] = Field(default_factory=list, description="除外セクター")

    @model_validator(mode="after")
    def check_disjoint(self) -> "SectorFilterConfig":
        overlap = set(self.include) & set(self.exclude)
        if overlap:
            raise ValueError(f"ambiguous sectors in both include and exclude: {sorted(overlap)}")
        return self


class FundamentalFilterConfig(BaseModel):
    min_revenue_growth: Optional[float] = Field(default=None, ge=-1, le=10, description="最低売上成長率")
    min_earnings_growth: Optional[float] = Field(default=None, ge=-1, le=10, description="最低利益成長率")
    max_forward_pe: Optional[float] = Field(default=None, gt=0, le=1000, description="最高予想PER")
    min_analyst_count: Optional[int] = Field(default=None, ge=0, le=100, description="最低アナリスト数")


class EarningsFilterConfig(BaseModel):
    exclude_days_before: Optional[int] = Field(default=None, ge=1, le=30, description="決算日前N日以内を除外")
    include_days_ahead: Optional[int] = Field(default=None, ge=1, le=30, description="決算日N日以内のみ含む")

    @model_validator(mode="after")
    def check_modes(self) -> "EarningsFilterConfig":
        if self.exclude_days_before is not None and self.include_days_ahead is not None:
            raise ValueError("exclude_days_before and include_days_ahead cannot both be set")
        return self


class FibonacciConfig(BaseModel):
    lookback: int = Field(default=60, ge=10, le=200, description="フィボナッチ・スイング検出ルックバック")


class CandlestickConfig(BaseModel):
    lookback: int = Field(default=5, ge=1, le=20, description="ローソク足パターン検出バー数")
    doji_threshold: float = Field(default=0.1, gt=0, le=1.0, description="ドジー判定閾値")
    marubozu_threshold: float = Field(default=0.9, gt=0, le=1.0, description="まるぼう判定閾値")


class BBSqueezeConfig(BaseModel):
    period: int = Field(default=20, ge=5, le=100, description="ボリンジャーバンド期間")
    std_dev: float = Field(default=2.0, gt=0, le=5.0, description="ボリンジャーバンド標準偏差")
    percentile_threshold: float = Field(default=20.0, gt=0, le=50.0, description="スクイーズ判定パーセンタイル閾値")


class PatternsConfig(BaseModel):
    enabled: bool = Field(default=False, description="パターンエンジン有効化（既定で無効）")
    fibonacci: FibonacciConfig = Field(default_factory=FibonacciConfig)
    candlestick: CandlestickConfig = Field(default_factory=CandlestickConfig)
    bb_squeeze: BBSqueezeConfig = Field(default_factory=BBSqueezeConfig)


class RegimeWeightsConfig(BaseModel):
    trend: float = Field(default=0.35, gt=0, le=1.0, description="トレンド信号の重み")
    breadth: float = Field(default=0.25, gt=0, le=1.0, description="ブレッドスIGNALの重み")
    volatility: float = Field(default=0.20, gt=0, le=1.0, description="ボラティリティ信号の重み")
    momentum: float = Field(default=0.20, gt=0, le=1.0, description="モメンタム信号の重み")

    @model_validator(mode="after")
    def check_weights_sum(self) -> "RegimeWeightsConfig":
        total = self.trend + self.breadth + self.volatility + self.momentum
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Regime weights must sum to 1.0, got {total}")
        return self


class RegimeConfig(BaseModel):
    enabled: bool = Field(default=False, description="レジームエンジン有効化（既定で無効）")
    benchmark: str = Field(default="SPY", description="ベンチマーク銘柄")
    weights: RegimeWeightsConfig = Field(default_factory=RegimeWeightsConfig)


class PositionSizingConfig(BaseModel):
    risk_per_trade_pct: float = Field(default=0.015, gt=0, le=0.1, description="1トレードあたりリスク比率")
    stop_atr_multiplier: float = Field(default=2.0, gt=0, le=10.0, description="ATRストップ乗数")
    atr_period: int = Field(default=14, ge=5, le=50, description="ATR計算期間")


class PortfolioRiskConfig(BaseModel):
    max_heat_pct: float = Field(default=0.06, gt=0, le=0.5, description="ポートフォリオ最大リスクヘート")
    max_sector_pct: float = Field(default=0.40, gt=0, le=1.0, description="セクター最大集中度")
    max_correlation: float = Field(default=0.70, gt=0, le=1.0, description="相関警告閾値")


class StopsConfig(BaseModel):
    trailing_pct: float = Field(default=0.05, gt=0, le=0.20, description="トレーリングストップ%")
    max_days_in_trade: int = Field(default=20, ge=1, le=100, description="タイムストップ日数")
    profit_time_threshold: float = Field(default=0.05, gt=0, le=0.5, description="タイムストップ回避閾値")


class RiskConfig(BaseModel):
    enabled: bool = Field(default=False, description="リスク管理有効化（既定で無効）")
    position_sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    portfolio: PortfolioRiskConfig = Field(default_factory=PortfolioRiskConfig)
    stops: StopsConfig = Field(default_factory=StopsConfig)


class MarketItemConfig(BaseModel):
    """Configuration for a single market (US stock, crypto, forex)."""
    name: str = Field(description="Market display name")
    type: str = Field(description="Market type: us_stock, crypto, forex")
    enabled: bool = Field(default=False, description="Enable this market (disabled by default)")
    tickers: List[str] = Field(default_factory=list, description="Ticker symbols for this market")
    period: str = Field(default="700d", description="yfinance data period")
    min_bars: int = Field(default=150, ge=10, le=1000, description="Minimum bars required")
    sector_label: Optional[str] = Field(default=None, description="Sector label for crypto/forex")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = ("us_stock", "crypto", "forex")
        if v not in allowed:
            raise ValueError(f"Market type must be one of {allowed}, got '{v}'")
        return v


class MarketsConfig(BaseModel):
    """Multi-market configuration. Opt-in, disabled by default."""
    enabled: bool = Field(default=False, description="Multi-market有効化（既定で無効）")
    markets_list: List[MarketItemConfig] = Field(default_factory=list, description="List of market definitions")


class FilterConfig(BaseModel):
    enabled: bool = Field(default=False, description="フィルタ有効化（既定で無効）")
    liquidity: LiquidityFilterConfig = Field(default_factory=LiquidityFilterConfig)
    market_cap: MarketCapFilterConfig = Field(default_factory=MarketCapFilterConfig)
    sector: SectorFilterConfig = Field(default_factory=SectorFilterConfig)
    fundamental: FundamentalFilterConfig = Field(default_factory=FundamentalFilterConfig)
    earnings: EarningsFilterConfig = Field(default_factory=EarningsFilterConfig)


class PipelineStrategiesConfig(BaseModel):
    vcp_breakout: bool = Field(default=False, description="VCPブレイクアウト戦略（既定で無効）")
    minervini: bool = Field(default=False, description="ミネルヴィニ・テンプレート戦略（既定で無効）")


class PipelineBacktestConfig(BaseModel):
    enabled: bool = Field(default=False, description="バックテスト付加レコード有効化（既定で無効）")


class PipelineConfig(BaseModel):
    enabled: bool = Field(default=False, description="パイプライン有効化（既定で無効）")
    rs: str = Field(default="legacy", description="RSプロバイダ（legacy|benchmark）")
    strategies: PipelineStrategiesConfig = Field(default_factory=PipelineStrategiesConfig)
    backtest: PipelineBacktestConfig = Field(default_factory=PipelineBacktestConfig)

    @field_validator("rs")
    @classmethod
    def validate_rs_provider(cls, v: str) -> str:
        if v not in ("legacy", "benchmark"):
            raise ValueError(f"rs must be 'legacy' or 'benchmark', got '{v}'")
        return v


class NotificationConfig(BaseModel):
    line_enabled: bool = Field(default=False, description="LINE通知有効化")
    line_chunk_size: int = Field(default=4000, ge=100, le=5000, description="メッセージ分割サイズ")


class ExportConfig(BaseModel):
    enabled: bool = Field(default=False, description="CSV/Excel出力有効化（既定で無効）")
    csv: bool = Field(default=True, description="CSV出力（有効時）")
    excel: bool = Field(default=True, description="Excel出力（有効時）")
    include_watchlist: bool = Field(default=True, description="Excelにウォッチリストシート追加")
    columns: Optional[List[str]] = Field(default=None, description="出力カラム（nullならデフォルト）")


class UIConfig(BaseModel):
    default_language: str = Field(default="ja", description="デフォルト言語")
    chart_days: int = Field(default=120, ge=30, le=365, description="チャート表示日数")
    news_limit: int = Field(default=8, ge=1, le=50, description="表示ニュース数")


class Config(BaseModel):
    """Main configuration container."""
    capital: CapitalConfig = Field(default_factory=CapitalConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    exit: ExitConfig = Field(default_factory=ExitConfig)
    vcp: VCPConfig = Field(default_factory=VCPConfig)
    rs: RSConfig = Field(default_factory=RSConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    ses: SESConfig = Field(default_factory=SESConfig)
    ecr: ECRConfig = Field(default_factory=ECRConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    markets: MarketsConfig = Field(default_factory=MarketsConfig)
    patterns: PatternsConfig = Field(default_factory=PatternsConfig)
    regime: RegimeConfig = Field(default_factory=RegimeConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    # Runtime values (not from config file)
    fmp_api_key: Optional[str] = Field(default=None, description="FMP API Key from env")
    deepseek_api_key: Optional[str] = Field(default=None, description="DeepSeek API Key from env")
    line_channel_token: Optional[str] = Field(default=None, description="LINE Channel Token from env")
    line_user_id: Optional[str] = Field(default=None, description="LINE User ID from env")

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """Load configuration from YAML file and environment variables."""
        # Default config path (project root config.yaml)
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "config.yaml"

        # Load YAML
        yaml_data: Dict[str, Any] = {}
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}

        # Load environment variables (override YAML)
        env_overrides = cls._load_env_overrides()

        # Merge: YAML -> env overrides
        merged = cls._deep_merge(yaml_data, env_overrides)

        # Create config instance
        config = cls(**merged)

        # Load secrets from environment
        config.fmp_api_key = os.getenv("FMP_API_KEY")
        config.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        config.line_channel_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        config.line_user_id = os.getenv("LINE_USER_ID")

        return config

    @classmethod
    def _load_env_overrides(cls) -> Dict[str, Any]:
        """Load configuration overrides from environment variables."""
        overrides = {}

        # Capital
        if cap := os.getenv("CAPITAL_JPY"):
            overrides.setdefault("capital", {})["jpy"] = int(cap)
        if mp := os.getenv("MAX_POSITIONS"):
            overrides.setdefault("capital", {})["max_positions"] = int(mp)
        if ar := os.getenv("ACCOUNT_RISK_PCT"):
            overrides.setdefault("capital", {})["account_risk_pct"] = float(ar)

        # Scan
        if rs := os.getenv("MIN_RS_RATING"):
            overrides.setdefault("scan", {})["min_rs_rating"] = int(rs)
        if vc := os.getenv("MIN_VCP_SCORE"):
            overrides.setdefault("scan", {})["min_vcp_score"] = int(vc)
        if pf := os.getenv("MIN_PROFIT_FACTOR"):
            overrides.setdefault("scan", {})["min_profit_factor"] = float(pf)

        # Exit
        if sl := os.getenv("STOP_LOSS_ATR"):
            overrides.setdefault("exit", {})["stop_loss_atr"] = float(sl)
        if tm := os.getenv("TARGET_R_MULTIPLE"):
            overrides.setdefault("exit", {})["target_r_multiple"] = float(tm)

        return overrides

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get_cache_expiry_seconds(self, cache_type: str) -> int:
        """Get cache expiry in seconds for a given cache type."""
        mapping = {
            "price": self.cache.price_expiry_hours * 3600,
            "fundamental": self.cache.fundamental_expiry_hours * 3600,
            "news": self.cache.news_expiry_hours * 3600,
            "insider": self.cache.insider_expiry_hours * 3600,
            "sector": self.cache.sector_expiry_days * 86400,
        }
        return mapping.get(cache_type, 3600)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance (singleton)."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance (for testing)."""
    global _config
    _config = config