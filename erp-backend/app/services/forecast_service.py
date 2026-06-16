"""需求预测服务 — Darts/Prophet 统一时序预测引擎

降级链: Prophet(>=30天) → Naive Seasonal(>=14天) → WMA(任意) → None(无数据)
"""

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import Settings, settings

logger = logging.getLogger(__name__)

# ── Darts 可选导入 ──────────────────────────────────────────────
_DARTS_AVAILABLE = False
try:
    from darts import TimeSeries
    from darts.models import NaiveSeasonal, Prophet as DartsProphet

    _DARTS_AVAILABLE = True
except ImportError:
    logger.info("[ForecastService] darts 未安装，预测功能不可用")


# ── 数据结构 ────────────────────────────────────────────────────

@dataclass
class ForecastResult:
    product_id: int
    model_used: str                   # "prophet" | "naive" | "wma_fallback" | "ensemble"
    forecast_mid: list[float]         # 点预测
    forecast_low: list[float]         # 下界
    forecast_high: list[float]        # 上界
    avg_daily_forecast: float         # 预测日均
    avg_daily_low: float              # 预测日均下界
    avg_daily_high: float             # 预测日均上界
    seasonality_detected: bool = False
    seasonality_type: str = "none"    # "weekly" | "yearly" | "both" | "none"
    data_points: int = 0
    confidence_score: float = 0.0     # 0.0-1.0
    fallback_reason: str | None = None


# ── 缓存抽象 ────────────────────────────────────────────────────

class CacheBackend(Protocol):
    """缓存后端协议，预留 Redis 等外部实现"""
    def get(self, key: int) -> ForecastResult | None: ...
    def set(self, key: int, value: ForecastResult, ttl: int = 0) -> None: ...
    def delete(self, key: int | None = None) -> None: ...


class MemoryCacheBackend:
    """默认内存缓存实现"""

    def __init__(self):
        self._store: dict[int, tuple[float, ForecastResult]] = {}
        self._lock = threading.Lock()

    def get(self, key: int) -> ForecastResult | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, result = entry
            ttl = settings.FORECAST_CACHE_TTL_HOURS * 3600
            if time.time() - ts > ttl:
                del self._store[key]
                return None
            return result

    def set(self, key: int, value: ForecastResult, ttl: int = 0) -> None:
        # ttl 参数预留，内存缓存使用全局配置
        with self._lock:
            self._store[key] = (time.time(), value)

    def delete(self, key: int | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


# ── ForecastService 类 ─────────────────────────────────────────

class ForecastService:
    """需求预测服务

    降级链: Prophet(>=30天) → Naive Seasonal(>=14天) → WMA(任意) → None(无数据)
    """

    def __init__(self, db: Session, config: Settings | None = None, cache: CacheBackend | None = None):
        self.db = db
        self.config = config or settings
        self.cache = cache or MemoryCacheBackend()
        # 延迟导入避免循环依赖
        self._model_selector = None
        self._weight_calculator = None

    @property
    def model_selector(self):
        if self._model_selector is None:
            from app.services.model_selector import ModelSelector
            self._model_selector = ModelSelector(self.db)
        return self._model_selector

    @property
    def weight_calculator(self):
        if self._weight_calculator is None:
            from app.services.model_selector import DynamicWeightCalculator
            self._weight_calculator = DynamicWeightCalculator(self.db)
        return self._weight_calculator

    # ── 公开接口 ────────────────────────────────────────────────

    def forecast(
        self,
        product_id: int,
        horizon_days: int = 0,
        model_override: str | None = None,
        force_refresh: bool = False,
    ) -> ForecastResult | None:
        """主入口：单产品需求预测

        Returns: ForecastResult 或 None（无数据/功能禁用）
        """
        if not self.config.FORECAST_ENABLED:
            return None

        horizon = horizon_days or self.config.FORECAST_HORIZON_DAYS

        # 查缓存
        if not force_refresh:
            cached = self.cache.get(product_id)
            if cached is not None:
                return cached

        # 读取产品级预测配置
        from app.models.product import Product
        product = self.db.get(Product, product_id)
        product_model = None
        product_seasonality = None
        if product is not None:
            if product.forecast_model and product.forecast_model != "auto":
                product_model = product.forecast_model
            if product.seasonality_type and product.seasonality_type != "auto":
                product_seasonality = product.seasonality_type

        # 产品级 forecast_model 优先于调用方传入的 model_override
        effective_override = product_model or model_override

        # 查数据
        df = self._fetch_daily_sales(product_id)
        data_points = len(df)

        # 完全无销量数据
        nonzero = (df["y"] > 0).sum()
        if nonzero == 0:
            return None

        # darts 不可用时的降级
        if not _DARTS_AVAILABLE:
            result = self._run_wma(df, horizon)
            result.fallback_reason = "darts 未安装，使用 WMA 回退"
            result.product_id = product_id
            self.cache.set(product_id, result)
            return result

        # 选模型 — 使用 ModelSelector，产品级配置优先
        selection = self.model_selector.select_model(product_id, data_points, effective_override)
        model_type = selection.model_name

        try:
            if model_type == "prophet":
                try:
                    result = self._run_prophet(df, horizon, seasonality_hint=product_seasonality)
                except Exception as e:
                    logger.warning(f"[Forecast] Prophet 失败 product={product_id}: {e}，降级为 naive")
                    result = self._run_naive(df, horizon)
                    result.fallback_reason = f"Prophet 失败: {e}"

            elif model_type == "naive":
                result = self._run_naive(df, horizon)

            elif model_type == "ensemble":
                prophet_r = None
                try:
                    prophet_r = self._run_prophet(df, horizon, seasonality_hint=product_seasonality)
                except Exception as e:
                    logger.warning(f"[Forecast] Ensemble 中 Prophet 失败: {e}")
                naive_r = self._run_naive(df, horizon)
                result = self._run_ensemble(prophet_r, naive_r, product_id=product_id)

            else:  # wma_fallback
                result = self._run_wma(df, horizon)

        except Exception as e:
            logger.error(f"[Forecast] 所有模型失败 product={product_id}: {e}")
            return None

        result.product_id = product_id

        # 应用置信度微调
        if result and selection.confidence_adjustment != 0:
            result.confidence_score = round(
                min(0.95, max(0.2, result.confidence_score + selection.confidence_adjustment)), 3
            )

        self.cache.set(product_id, result)
        return result

    def forecast_batch(
        self,
        product_ids: list[int],
        horizon_days: int = 0,
    ) -> dict[int, ForecastResult]:
        """批量预测：优先缓存，未命中则逐个计算"""
        results: dict[int, ForecastResult] = {}
        horizon = horizon_days or self.config.FORECAST_HORIZON_DAYS

        for pid in product_ids:
            cached = self.cache.get(pid)
            if cached is not None:
                results[pid] = cached
                continue
            result = self.forecast(pid, horizon_days=horizon)
            if result is not None:
                results[pid] = result

        return results

    # ── 缓存方法 ────────────────────────────────────────────────

    def _get_cached(self, product_id: int) -> ForecastResult | None:
        return self.cache.get(product_id)

    def _set_cached(self, product_id: int, result: ForecastResult) -> None:
        self.cache.set(product_id, result)

    def invalidate_cache(self, product_id: int | None = None) -> None:
        """清除指定产品或全部缓存"""
        self.cache.delete(product_id)

    # ── 数据查询 ────────────────────────────────────────────────

    def _fetch_daily_sales(self, product_id: int, days: int = 365) -> pd.DataFrame:
        """查询产品每日销量，返回 DataFrame[ds, y]，ds=date, y=quantity

        对零销售日自动补零，保证时间序列连续。
        默认 365 天以支持 Prophet 检测 yearly seasonality。
        """
        from sqlalchemy import func
        from app.models.sale import SaleOrder, SaleOrderItem

        cutoff = date.today() - timedelta(days=days)
        rows = (
            self.db.query(
                func.date(SaleOrder.order_date).label("d"),
                func.sum(SaleOrderItem.quantity).label("qty"),
            )
            .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
            .filter(
                SaleOrder.order_date >= cutoff,
                SaleOrderItem.product_id == product_id,
                SaleOrder.status != "cancelled",
            )
            .group_by(func.date(SaleOrder.order_date))
            .all()
        )

        # 构建连续日期序列
        sales_map: dict[str, float] = {}
        for r in rows:
            d = r.d
            if isinstance(d, str):
                d = d[:10]
            else:
                d = str(d)
            sales_map[d] = float(r.qty or 0)

        today = date.today()
        dates = []
        values = []
        current = cutoff
        while current <= today:
            ds = current.strftime("%Y-%m-%d")
            dates.append(ds)
            values.append(sales_map.get(ds, 0.0))
            current += timedelta(days=1)

        return pd.DataFrame({"ds": dates, "y": values})

    # ── 模型选择 ────────────────────────────────────────────────

    def _pick_model(self, data_points: int, model_override: str | None = None) -> str:
        """根据数据量和配置选择模型

        .. deprecated::
            使用 ModelSelector.select_model 替代。本方法保留仅为向后兼容。
        """
        if model_override and model_override != "auto":
            if model_override == "prophet" and data_points < self.config.FORECAST_MIN_DATA_DAYS:
                logger.warning(
                    f"[Forecast] Prophet 需要 >= {self.config.FORECAST_MIN_DATA_DAYS} 天数据，"
                    f"实际 {data_points}，降级为 naive"
                )
                return "naive"
            return model_override

        model_setting = self.config.FORECAST_MODEL
        if model_setting and model_setting != "auto":
            return model_setting

        min_days = self.config.FORECAST_MIN_DATA_DAYS
        if data_points >= min_days:
            return "prophet"
        elif data_points >= 14:
            return "naive"
        else:
            return "wma_fallback"

    # ── Prophet 预测 ────────────────────────────────────────────

    def _run_prophet(self, df: pd.DataFrame, horizon: int, seasonality_hint: str | None = None) -> ForecastResult:
        """Darts Prophet 包装，支持中国节假日和自适应季节性

        Args:
            seasonality_hint: 产品级季节性配置 ("weekly"/"yearly"/"both"/"none")，
                              覆盖基于数据量的自动判断
        """
        if not _DARTS_AVAILABLE:
            raise RuntimeError("darts 未安装")

        data_days = len(df)

        # 季节性配置：产品级 hint 优先，否则按数据量自动判断
        if seasonality_hint and seasonality_hint != "auto":
            yearly = seasonality_hint in ("yearly", "both")
            weekly = seasonality_hint in ("weekly", "both")
        else:
            yearly = data_days >= 365
            weekly = data_days >= 14

        model = DartsProphet(
            add_seasonalities={
                **({"yearly": True} if yearly else {}),
                **({"weekly": True} if weekly else {}),
            },
            country_holidays="CN",
        )

        series = TimeSeries.from_dataframe(df, time_col="ds", value_cols="y")
        model.fit(series)

        # 概率预测获取置信区间
        pred = model.predict(n=horizon, num_samples=200)
        mid_values = pred.mean(axis=1).values().flatten().tolist()
        low_values = pred.quantile(0.1, axis=1).values().flatten().tolist()
        high_values = pred.quantile(0.9, axis=1).values().flatten().tolist()

        # 季节性检测
        seasonality_type = "none"
        if yearly and weekly:
            seasonality_type = "both"
        elif yearly:
            seasonality_type = "yearly"
        elif weekly:
            seasonality_type = "weekly"

        confidence = self._calc_confidence(mid_values, low_values, high_values, data_days)

        return ForecastResult(
            product_id=0,  # caller fills
            model_used="prophet",
            forecast_mid=[max(0.0, v) for v in mid_values],
            forecast_low=[max(0.0, v) for v in low_values],
            forecast_high=[max(0.0, v) for v in high_values],
            avg_daily_forecast=float(np.mean(mid_values)),
            avg_daily_low=float(np.mean(low_values)),
            avg_daily_high=float(np.mean(high_values)),
            seasonality_detected=seasonality_type != "none",
            seasonality_type=seasonality_type,
            data_points=data_days,
            confidence_score=confidence,
        )

    # ── Naive Seasonal 预测 ─────────────────────────────────────

    def _run_naive(self, df: pd.DataFrame, horizon: int) -> ForecastResult:
        """季节朴素预测：上周同日 + 短期趋势调整"""
        y = df["y"].values
        n = len(y)

        mid = []
        low = []
        high = []

        # 短期趋势：最近 7 天均值 vs 前 7 天均值
        if n >= 14:
            recent_avg = np.mean(y[-7:])
            prev_avg = np.mean(y[-14:-7])
            trend_ratio = recent_avg / max(prev_avg, 0.01)
            trend_ratio = max(0.7, min(1.3, trend_ratio))
        else:
            trend_ratio = 1.0

        # 用训练数据的标准差计算置信区间
        std = float(np.std(y)) if len(y) >= 2 else float(np.mean(y) * 0.3 + 1.0)
        z_score = 1.28  # 80% 置信区间

        for i in range(horizon):
            # 上周同日
            if n >= 7:
                base = y[-(7 - (i % 7))] if i < 7 else y[-7 + (i % 7)]
            else:
                base = np.mean(y) if n > 0 else 0.0
            val = max(0.0, base * trend_ratio)
            mid.append(val)

            # 置信区间：基于历史标准差
            spread = z_score * std
            low.append(max(0.0, val - spread))
            high.append(val + spread)

        confidence = self._calc_confidence(mid, low, high, n)

        avg_mid = float(np.mean(mid))

        return ForecastResult(
            product_id=0,
            model_used="naive",
            forecast_mid=mid,
            forecast_low=low,
            forecast_high=high,
            avg_daily_forecast=avg_mid,
            avg_daily_low=float(np.mean(low)),
            avg_daily_high=float(np.mean(high)),
            seasonality_detected=True,
            seasonality_type="weekly",
            data_points=n,
            confidence_score=confidence,
        )

    # ── WMA 回退预测 ────────────────────────────────────────────

    def _run_wma(self, df: pd.DataFrame, horizon: int) -> ForecastResult:
        """7 日加权移动平均 + 振荡"""
        y = df["y"].values
        wma_weights = [0.05, 0.08, 0.12, 0.15, 0.18, 0.22, 0.20]
        last7 = y[-7:].tolist() if len(y) >= 7 else y.tolist()
        w = wma_weights[-len(last7):]
        wma = sum(wi * v for wi, v in zip(w, last7)) / sum(w)

        avg7 = sum(last7) / len(last7)
        std7 = (sum((v - avg7) ** 2 for v in last7) / len(last7)) ** 0.5 if len(last7) >= 2 else 0.0
        volatility = std7 * 0.3

        mid = [max(0.0, wma + math.sin(i * 2.7 + 1.3) * volatility) for i in range(horizon)]
        spread = max(wma * 0.3, volatility * 2, 1.0)
        low = [max(0.0, v - spread) for v in mid]
        high = [v + spread for v in mid]

        confidence = self._calc_confidence(mid, low, high, len(y))

        avg_mid = float(np.mean(mid)) if mid else 0.0

        return ForecastResult(
            product_id=0,
            model_used="wma_fallback",
            forecast_mid=mid,
            forecast_low=low,
            forecast_high=high,
            avg_daily_forecast=avg_mid,
            avg_daily_low=float(np.mean(low)),
            avg_daily_high=float(np.mean(high)),
            seasonality_detected=False,
            seasonality_type="none",
            data_points=len(y),
            confidence_score=confidence,
            fallback_reason="数据不足，使用 WMA 回退",
        )

    # ── 集成预测 ────────────────────────────────────────────────

    def _run_ensemble(
        self,
        prophet_result: ForecastResult | None,
        naive_result: ForecastResult,
        product_id: int = 0,
    ) -> ForecastResult:
        """融合 Prophet + Naive：权重由 DynamicWeightCalculator 动态决定"""
        if prophet_result is None:
            return naive_result

        # 动态权重
        seasonality = prophet_result.seasonality_detected
        weights = self.weight_calculator.calc_ensemble_weights(
            product_id=product_id or prophet_result.product_id,
            seasonality_detected=seasonality,
        )
        w = weights.get("prophet", 0.5)
        n = min(len(prophet_result.forecast_mid), len(naive_result.forecast_mid))
        horizon = n

        mid = [w * prophet_result.forecast_mid[i] + (1 - w) * naive_result.forecast_mid[i] for i in range(horizon)]
        # 置信区间加权融合（替代原来的 min/max 取极值）
        low = [w * prophet_result.forecast_low[i] + (1 - w) * naive_result.forecast_low[i] for i in range(horizon)]
        high = [w * prophet_result.forecast_high[i] + (1 - w) * naive_result.forecast_high[i] for i in range(horizon)]

        avg_mid = float(np.mean(mid))
        p_conf = prophet_result.confidence_score
        n_conf = naive_result.confidence_score
        blended_conf = w * p_conf + (1 - w) * n_conf

        return ForecastResult(
            product_id=prophet_result.product_id,
            model_used="ensemble",
            forecast_mid=[max(0.0, v) for v in mid],
            forecast_low=[max(0.0, v) for v in low],
            forecast_high=high,
            avg_daily_forecast=avg_mid,
            avg_daily_low=float(np.mean(low)),
            avg_daily_high=float(np.mean(high)),
            seasonality_detected=prophet_result.seasonality_detected or naive_result.seasonality_detected,
            seasonality_type=prophet_result.seasonality_type if prophet_result.seasonality_detected else naive_result.seasonality_type,
            data_points=max(prophet_result.data_points, naive_result.data_points),
            confidence_score=round(blended_conf, 3),
        )

    # ── 置信度计算 ──────────────────────────────────────────────

    @staticmethod
    def _calc_confidence(
        mid_values: list[float],
        low_values: list[float],
        high_values: list[float],
        data_points: int,
    ) -> float:
        """基于变异系数 + 数据量计算置信度

        使用 sigmoid 函数代替硬编码魔法数字：
        cv=0.2 → ~0.9, cv=0.5 → ~0.7, cv=1.0 → ~0.5, cv=2.0 → ~0.3
        """
        avg_spread = np.mean([h - l for h, l in zip(high_values, low_values)])
        avg_mid = np.mean(mid_values) if mid_values else 1.0
        cv = avg_spread / max(avg_mid, 0.01)

        # sigmoid: cv越小 → 置信越高
        raw = 1.0 / (1.0 + math.exp(2.0 * (cv - 0.5)))

        # 数据量加成：每多100天加0.02，上限0.1
        data_bonus = min(0.1, data_points / 100 * 0.02)

        return round(min(0.95, max(0.2, raw + data_bonus)), 3)


# ── 模块级便捷函数（向后兼容） ─────────────────────────────────

_shared_cache = MemoryCacheBackend()


def _get_service(db: Session) -> ForecastService:
    """使用共享缓存，跨请求复用预测结果"""
    return ForecastService(db, cache=_shared_cache)


def forecast_product_demand(
    product_id: int,
    db: Session,
    horizon_days: int = 0,
    model_override: str | None = None,
    force_refresh: bool = False,
) -> ForecastResult | None:
    """主入口：单产品需求预测（向后兼容包装）"""
    return _get_service(db).forecast(product_id, horizon_days, model_override, force_refresh)


def forecast_batch_demand(
    product_ids: list[int],
    db: Session,
    horizon_days: int = 0,
) -> dict[int, ForecastResult]:
    """批量预测（向后兼容包装）"""
    return _get_service(db).forecast_batch(product_ids, horizon_days)


def get_cached_forecast(product_id: int) -> ForecastResult | None:
    """从共享缓存获取预测结果"""
    return _shared_cache.get(product_id)


def invalidate_forecast_cache(product_id: int | None = None) -> None:
    """清除共享缓存"""
    _shared_cache.delete(product_id)
