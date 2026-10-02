"""权重口径：入表资格、正整数校验、生成时快照。

口径（唯一）：仅 data_quality='clean' 且 weight 为正整数的任务可入表；
任何候选任务 weight<=0 / 非整数 → 整次生成拒绝，不写任何格子。
"""

# 入表任务的数据质量门槛
CLEAN_QUALITY = "clean"


class WeightValidationError(ValueError):
    """权重不满足入表口径，整次生成必须失败。"""


def coerce_int(weight) -> int:
    """正整数校验，0、负数、非整数、无法转 int 一律拒绝。"""
    iw = as_int(weight)
    if iw <= 0:
        raise WeightValidationError(f"non_positive_weight:{iw}")
    return iw


def as_int(weight) -> int:
    """整数转换（允许 0/负，weight<=0 的任务可落库但不可入表）。"""
    if isinstance(weight, bool):
        raise WeightValidationError(f"invalid_weight:{weight!r}")
    try:
        iw = int(weight)
    except (TypeError, ValueError):
        raise WeightValidationError(f"invalid_weight:{weight!r}")
    if float(weight) != float(iw):
        raise WeightValidationError(f"invalid_weight:{weight!r}")
    return iw


def assert_generatable(task_rows: list[dict]) -> dict[int, int]:
    """对全部 clean 任务做校验，返回 {task_id: weight} 快照。

    脏任务不参与（调用方只传 clean 行）；clean 任务中只要有 weight<=0
    即整次拒绝，由调用方放弃落库。
    """
    snapshot: dict[int, int] = {}
    bad: list[tuple[int, object]] = []
    for r in task_rows:
        tid = r["id"] if "id" in r else r["task_id"]
        try:
            snapshot[tid] = coerce_int(r["weight"])
        except WeightValidationError:
            bad.append((tid, r["weight"]))
    if bad:
        raise WeightValidationError(f"rejected_tasks:{bad}")
    return snapshot


def snapshot_from_rows(task_rows: list[dict]) -> dict[int, int]:
    """读取已落库的周快照行 [{task_id, weight}] → dict。"""
    return {int(r["task_id"]): int(r["weight"]) for r in task_rows}
