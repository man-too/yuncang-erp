"""回测引擎 — 用历史数据评估各预测模型表现"""

import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """单个模型在单个产品上的回测结果"""
    product_id: int
    model_name: str                    # "prophet" | "naive" | "wma_fallback" | "ensemble"
    mape: float                        # Mean Absolute Percentage Error
    wmape: float                       # Weighted MAPE
    smape: float                       # Symmetric MAPE
    data_points: int                   # 训练数据量
    train_window: int                  # 训练窗口天数
    test_window: int                   # 测试窗口天数
    run_time_ms: float = 0.0           # 回测耗时
    error: str | None = None           # 失败原因


@dataclass
class ProductBacktestReport:
    """单个产品所有模型的回测报告"""
    product_id: int
    results: list[BacktestResult] = field(default_factory=list)
    best_model: str = ""               # WMAPE 最低的模型名
    best_wmape: float = 1.0

    def compute_best(self) -> None:
        """根据 WMAPE 选出最佳模型"""
        valid = [r for r in self.results if r.error is None]
        if valid:
            best = min(valid, key=lambda r: r.wmape)
            self.best_model = best.model_name
            self.best_wmape = best.wmape


class BacktestCacheBackend(Protocol):
    def get(self, product_id: int) -> ProductBacktestReport | None: ...
    def set(self, product_id: int, report: ProductBacktestReport) -> None: ...
    def clear(self) -> None: ...


class MemoryBacktestCache:
    def __init__(self, ttl_hours: int = 24):
        self._store: dict[int, tuple[float, ProductBacktestReport]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_hours * 3600

    def get(self, product_id: int) -> ProductBacktestReport | None:
        with self._lock:
            entry = self._store.get(product_id)
            if entry is None:
                return None
            ts, report = entry
            if time.time() - ts > self._ttl:
                del self._store[product_id]
                return None
            return report

    def set(self, product_id: int, report: ProductBacktestReport) -> None:
        with self._lock:
            self._store[product_id] = (time.time(), report)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class BacktestService:
    """回测引擎 — 评估各预测模型在历史数据上的表现"""

    DEFAULT_TRAIN_DAYS = 60
    DEFAULT_TEST_DAYS = 14
    ALL_MODELS = ["prophet", "naive", "wma_fallback"]

    def __init__(self, db: Session, cache: BacktestCacheBackend | None = None):
        self.db = db
        self.cache = cache or MemoryBacktestCache()

    def run_backtest(
        self,
        product_id: int,
        train_days: int = 0,
        test_days: int = 0,
        models: list[str] | None = None,
        force_refresh: bool = False,
    ) -> ProductBacktestReport:
        """对单个产品跑回测

        Args:
            product_id: 产品ID
            train_days: 训练窗口天数，默认60
            test_days: 测试窗口天数，默认14
            models: 要测试的模型列表，默认全部
            force_refresh: 是否强制刷新缓存
        """
        # 查缓存
        if not force_refresh:
            cached = self.cache.get(product_id)
            if cached is not None:
                return cached

        train_w = train_days or self.DEFAULT_TRAIN_DAYS
        test_w = test_days or self.DEFAULT_TEST_DAYS
        model_list = models or self.ALL_MODELS

        # 获取历史数据
        df = self._fetch_history(product_id, days=train_w + test_w)
        if df.empty or len(df) < test_w + 7:
            report = ProductBacktestReport(product_id=product_id)
            report.results = [
                BacktestResult(
                    product_id=product_id, model_name=m,
                    mape=1.0, wmape=1.0, smape=1.0,
                    data_points=len(df), train_window=train_w, test_window=test_w,
                    error="数据不足，无法回测"
                )
                for m in model_list
            ]
            self.cache.set(product_id, report)
            return report

        # 切分训练/测试
        train_df = df.iloc[:-test_w].copy()
        test_df = df.iloc[-test_w:].copy()
        actual = test_df["y"].values.tolist()

        report = ProductBacktestReport(product_id=product_id)

        for model_name in model_list:
            result = self._backtest_single_model(
                product_id, model_name, train_df, actual, train_w, test_w
            )
            report.results.append(result)

        report.compute_best()
        self.cache.set(product_id, report)
        return report

    def run_batch_backtest(
        self,
        product_ids: list[int],
        train_days: int = 0,
        test_days: int = 0,
        models: list[str] | None = None,
        force_refresh: bool = False,
    ) -> dict[int, ProductBacktestReport]:
        """批量回测"""
        results = {}
        for pid in product_ids:
            results[pid] = self.run_backtest(pid, train_days, test_days, models, force_refresh)
        return results

    def get_best_model(self, product_id: int) -> str | None:
        """获取产品回测表现最好的模型名"""
        report = self.cache.get(product_id)
        if report and report.best_model:
            return report.best_model
        return None

    # ── 内部方法 ──

    def _backtest_single_model(
        self,
        product_id: int,
        model_name: str,
        train_df: pd.DataFrame,
        actual: list[float],
        train_w: int,
        test_w: int,
    ) -> BacktestResult:
        """对单个模型跑回测"""
        start_ms = time.time() * 1000

        try:
            from app.services.forecast_service import ForecastService
            svc = ForecastService(self.db)

            # 根据模型名选择方法
            horizon = len(actual)
            # P0-2 修复：回测时传 as_of_date=训练窗口最后日期，避免促销 lookahead bias
            train_last_date = None
            if not train_df.empty:
                last_ds = train_df["ds"].iloc[-1]
                if hasattr(last_ds, "date"):
                    train_last_date = last_ds.date()
                elif isinstance(last_ds, str):
                    try:
                        train_last_date = date.fromisoformat(last_ds[:10])
                    except ValueError:
                        train_last_date = None
                else:
                    try:
                        train_last_date = date.fromisoformat(str(last_ds)[:10])
                    except ValueError:
                        train_last_date = None

            if model_name == "prophet":
                result = svc._run_prophet(train_df, horizon, product_id=product_id, as_of_date=train_last_date)
            elif model_name == "naive":
                result = svc._run_naive(train_df, horizon)
            elif model_name == "wma_fallback":
                result = svc._run_wma(train_df, horizon)
            else:
                return BacktestResult(
                    product_id=product_id, model_name=model_name,
                    mape=1.0, wmape=1.0, smape=1.0,
                    data_points=len(train_df), train_window=train_w, test_window=test_w,
                    error=f"未知模型: {model_name}"
                )

            forecast = result.forecast_mid[:len(actual)]
            mape = self._calc_mape(actual, forecast)
            wmape = self._calc_wmape(actual, forecast)
            smape = self._calc_smape(actual, forecast)
            run_ms = time.time() * 1000 - start_ms

            return BacktestResult(
                product_id=product_id, model_name=model_name,
                mape=round(mape, 4), wmape=round(wmape, 4), smape=round(smape, 4),
                data_points=len(train_df), train_window=train_w, test_window=test_w,
                run_time_ms=round(run_ms, 1),
            )
        except Exception as e:
            logger.warning(f"[Backtest] {model_name} failed for product {product_id}: {e}")
            return BacktestResult(
                product_id=product_id, model_name=model_name,
                mape=1.0, wmape=1.0, smape=1.0,
                data_points=len(train_df), train_window=train_w, test_window=test_w,
                error=str(e)
            )

    def _fetch_history(self, product_id: int, days: int = 74) -> pd.DataFrame:
        """获取历史销量数据（复用 ForecastService 的数据查询逻辑）"""
        from app.services.forecast_service import ForecastService
        svc = ForecastService(self.db)
        return svc._fetch_daily_sales(product_id, days=days)

    # ── 误差指标 ──

    @staticmethod
    def _calc_mape(actual: list[float], forecast: list[float]) -> float:
        """MAPE = mean(|actual - forecast| / |actual|) * 100%
        跳过 actual=0 的点
        """
        errors = []
        for a, f in zip(actual, forecast):
            if abs(a) > 1e-8:
                errors.append(abs(a - f) / abs(a))
        return sum(errors) / len(errors) if errors else 1.0

    @staticmethod
    def _calc_wmape(actual: list[float], forecast: list[float]) -> float:
        """WMAPE = sum(|actual - forecast|) / sum(|actual|)
        比 MAPE 更稳定，不受零值影响
        """
        denom = sum(abs(a) for a in actual)
        if denom < 1e-8:
            return 1.0
        numer = sum(abs(a - f) for a, f in zip(actual, forecast))
        return numer / denom

    @staticmethod
    def _calc_smape(actual: list[float], forecast: list[float]) -> float:
        """SMAPE = mean(2*|actual-forecast| / (|actual|+|forecast|)) * 100%
        对称版本，避免 MAPE 的偏斜
        """
        errors = []
        for a, f in zip(actual, forecast):
            denom = abs(a) + abs(f)
            if denom > 1e-8:
                errors.append(2 * abs(a - f) / denom)
        return sum(errors) / len(errors) if errors else 1.0
