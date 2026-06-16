"""智能模型选择器 + 动态权重计算器

替代 ForecastService._pick_model 的硬编码逻辑：
- 优先查回测结果，选 WMAPE 最低的模型
- 无回测结果时，按数据量降级（保留原逻辑作为 fallback）
- Ensemble 权重根据各模型 WMAPE 反比计算
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ModelSelection:
    """模型选择结果"""
    model_name: str                    # 选中的模型名
    confidence_adjustment: float       # 基于回测表现的置信度微调 (-0.1 ~ +0.1)
    selection_reason: str              # 选择原因说明
    ensemble_weights: dict[str, float] | None = None  # ensemble 模式下各模型权重


class ModelSelector:
    """智能模型选择器 — 根据回测表现或数据量选择最佳预测模型"""

    # 数据量阈值（与原 _pick_model 保持一致作为 fallback）
    PROPHET_MIN_DAYS = 30
    NAIVE_MIN_DAYS = 14

    def __init__(self, db: Session):
        self.db = db

    def select_model(
        self,
        product_id: int,
        data_points: int,
        model_override: str | None = None,
    ) -> ModelSelection:
        """选择最佳预测模型

        优先级：
        1. 用户指定 model_override（非 auto）→ 直接使用
        2. 查回测结果 → 选 WMAPE 最低的模型
        3. 无回测 → 按数据量降级

        Args:
            product_id: 产品ID
            data_points: 可用数据天数
            model_override: 用户指定模型 ("auto" | "prophet" | "naive" | "wma" | "ensemble")
        """
        # 1. 用户指定
        if model_override and model_override != "auto":
            name = model_override
            if name == "wma":
                name = "wma_fallback"
            # 检查数据量是否满足
            if name == "prophet" and data_points < self.PROPHET_MIN_DAYS:
                logger.warning(f"[ModelSelector] Prophet 需要 >= {self.PROPHET_MIN_DAYS} 天，实际 {data_points}，降级为 naive")
                return ModelSelection(
                    model_name="naive",
                    confidence_adjustment=-0.05,
                    selection_reason=f"用户指定 Prophet 但数据不足({data_points}<{self.PROPHET_MIN_DAYS})，降级为 Naive"
                )
            return ModelSelection(
                model_name=name,
                confidence_adjustment=0.0,
                selection_reason=f"用户指定模型: {name}"
            )

        # 2. 查回测结果
        best = self._check_backtest(product_id)
        if best is not None:
            return best

        # 3. 按数据量降级（原逻辑）
        return self._fallback_by_data(data_points)

    def _check_backtest(self, product_id: int) -> ModelSelection | None:
        """查回测缓存，选最佳模型"""
        try:
            from app.services.backtest_service import BacktestService
            svc = BacktestService(self.db)
            report = svc.cache.get(product_id)
            if report is None:
                return None

            if not report.best_model or report.best_wmape >= 1.0:
                return None

            # 回测表现好的模型，微调置信度
            # WMAPE < 0.1 → +0.1, WMAPE < 0.2 → +0.05, WMAPE < 0.3 → 0, WMAPE >= 0.3 → -0.05
            if report.best_wmape < 0.1:
                adj = 0.1
            elif report.best_wmape < 0.2:
                adj = 0.05
            elif report.best_wmape < 0.3:
                adj = 0.0
            else:
                adj = -0.05

            return ModelSelection(
                model_name=report.best_model,
                confidence_adjustment=adj,
                selection_reason=f"回测最优: {report.best_model} (WMAPE={report.best_wmape:.3f})"
            )
        except Exception as e:
            logger.debug(f"[ModelSelector] Backtest lookup failed: {e}")
            return None

    def _fallback_by_data(self, data_points: int) -> ModelSelection:
        """按数据量降级选择（原 _pick_model 逻辑）"""
        min_days = getattr(settings, 'FORECAST_MIN_DATA_DAYS', 30)

        if data_points >= min_days:
            return ModelSelection(
                model_name="prophet",
                confidence_adjustment=0.0,
                selection_reason=f"数据充足({data_points}天)，使用 Prophet"
            )
        elif data_points >= self.NAIVE_MIN_DAYS:
            return ModelSelection(
                model_name="naive",
                confidence_adjustment=-0.05,
                selection_reason=f"数据不足Prophet({data_points}天)，降级为 Naive"
            )
        else:
            return ModelSelection(
                model_name="wma_fallback",
                confidence_adjustment=-0.1,
                selection_reason=f"数据不足Naive({data_points}天)，降级为 WMA"
            )


class DynamicWeightCalculator:
    """动态权重计算器 — 根据回测表现计算 ensemble 权重"""

    # 无回测数据时的默认权重
    DEFAULT_WEIGHTS_SEASONAL = {"prophet": 0.7, "naive": 0.3}
    DEFAULT_WEIGHTS_NO_SEASONAL = {"prophet": 0.5, "naive": 0.5}

    def __init__(self, db: Session):
        self.db = db

    def calc_ensemble_weights(
        self,
        product_id: int,
        seasonality_detected: bool = False,
    ) -> dict[str, float]:
        """计算 ensemble 权重

        逻辑：
        1. 查回测结果，根据 WMAPE 反比计算权重
        2. 无回测 → 使用默认权重

        反比权重：weight_i = (1/wmape_i) / sum(1/wmape_j)
        """
        # 查回测
        backtest_weights = self._weights_from_backtest(product_id)
        if backtest_weights is not None:
            return backtest_weights

        # Fallback
        if seasonality_detected:
            return dict(self.DEFAULT_WEIGHTS_SEASONAL)
        else:
            return dict(self.DEFAULT_WEIGHTS_NO_SEASONAL)

    def _weights_from_backtest(self, product_id: int) -> dict[str, float] | None:
        """从回测结果计算反比权重"""
        try:
            from app.services.backtest_service import BacktestService
            svc = BacktestService(self.db)
            report = svc.cache.get(product_id)
            if report is None:
                return None

            # 收集有效模型的 WMAPE
            model_wmapes: dict[str, float] = {}
            for r in report.results:
                if r.error is None and r.model_name in ("prophet", "naive"):
                    model_wmapes[r.model_name] = max(r.wmape, 0.01)  # 避免除零

            if len(model_wmapes) < 2:
                return None

            # 反比权重
            inv_wmapes = {m: 1.0 / w for m, w in model_wmapes.items()}
            total = sum(inv_wmapes.values())
            weights = {m: round(v / total, 3) for m, v in inv_wmapes.items()}

            # 确保权重和为 1.0
            weight_sum = sum(weights.values())
            if abs(weight_sum - 1.0) > 0.001:
                max_model = max(weights, key=weights.get)
                weights[max_model] = round(weights[max_model] + (1.0 - weight_sum), 3)

            logger.info(f"[DynamicWeight] Product {product_id}: {weights} (from backtest WMAPE: {model_wmapes})")
            return weights
        except Exception as e:
            logger.debug(f"[DynamicWeight] Backtest lookup failed: {e}")
            return None
