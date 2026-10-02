"""编排：取活跃 clean 成员 + clean 任务权重快照 → 展平格子 → 余数填人。

只做纯计算，不碰数据库；落库见 persistence.py。
"""

from .weights import assert_generatable
from .remainder import assign_with_remainder


def flatten_cells(weights: dict[int, int], days: int) -> list[dict]:
    """按 日 → 任务(id 升序) → 格序号 展平。

    同一任务一天占 weight 格，slot_index∈[0,weight) 是格位身份。
    """
    cells = []
    for day in range(days):
        for tid in sorted(weights):
            for slot_index in range(weights[tid]):
                cells.append({"day": day, "task_id": tid, "slot_index": slot_index})
    return cells


def plan_week(member_ids: list[int], clean_task_rows: list[dict], days: int = 7) -> dict:
    """返回 {slots, weights, total, days}。

    clean 任务中存在 weight<=0 时抛 WeightValidationError，调用方必须
    整次放弃（旧 assignments 行数保持不变）。
    """
    weights = assert_generatable(clean_task_rows)
    cells = flatten_cells(weights, days)
    if not member_ids or not cells:
        return {"slots": [], "weights": weights, "total": 0, "days": days}
    slots = assign_with_remainder(cells, member_ids)
    return {"slots": slots, "weights": weights, "total": len(slots), "days": days}
