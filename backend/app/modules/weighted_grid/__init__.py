"""加权占格模块：权重口径 / 余数策略 / 编排 / 落库彼此分文件。"""
from .weights import (
    WeightValidationError,
    snapshot_from_rows,
    assert_generatable,
    as_int,
    coerce_int,
)
from .remainder import POLICY, POLICY_LABEL, assign_with_remainder
from .planner import plan_week
from .persistence import replace_generation, week_snapshot, week_workload

__all__ = [
    "WeightValidationError",
    "snapshot_from_rows",
    "assert_generatable",
    "as_int",
    "coerce_int",
    "POLICY",
    "POLICY_LABEL",
    "assign_with_remainder",
    "plan_week",
    "replace_generation",
    "week_snapshot",
    "week_workload",
]
