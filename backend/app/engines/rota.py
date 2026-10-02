"""Round-robin weekly chore assignments + swap legality.

加权占格的口径/余数/落库实现已拆到 app.modules.weighted_grid；
本文件保留兼容入口（旧测例与外部导入仍可用），口径全部委托模块，
避免两份实现漂移。
"""
from app.modules.weighted_grid.weights import WeightValidationError as WeightError
from app.modules.weighted_grid.weights import coerce_int as validate_weight
from app.modules.weighted_grid.remainder import (
    POLICY as REMAINDER_POLICY,
    POLICY_LABEL as REMAINDER_POLICY_LABEL,
    assign_with_remainder as _assign,
)
from app.modules.weighted_grid.planner import flatten_cells as _flatten_cells


def build_weighted_cells(task_weights: dict[int, int], days: int = 7) -> list[dict]:
    """按 日→任务→格序号 展平格子（不含 member_id）。"""
    return _flatten_cells(task_weights, days)


def build_week_slots(member_ids: list[int], task_weights: dict[int, int] | list[int],
                     days: int = 7) -> list[dict]:
    """加权周表入口；兼容旧签名：传 task_ids 列表时各任务权重视为 1。

    weight 全为 1 时结果与改造前逐格一致（(day, task_id, slot_index=0,
    member_id) 去掉 slot_index 即旧布局）。
    """
    if isinstance(task_weights, list):
        task_weights = {tid: 1 for tid in task_weights}
    task_weights = {tid: validate_weight(w) for tid, w in task_weights.items()}
    cells = build_weighted_cells(task_weights, days)
    if not member_ids:
        return []
    return _assign(cells, member_ids)


def validate_weights(task_weights: dict[int, int]) -> dict[int, int]:
    """权重口径校验：weight<=0 / 非正整数即拒（整次生成由上层放弃）。"""
    return {tid: validate_weight(w) for tid, w in task_weights.items()}


def workloads(slots: list[dict], member_ids: list[int] | None = None) -> dict[int, int]:
    """按同一份 slots 统计成员当周负荷（看板/成员页同口径）。"""
    out = {m: 0 for m in (member_ids or [])}
    for s in slots:
        out[s["member_id"]] = out.get(s["member_id"], 0) + 1
    return out


def swap_legal(slots: list[dict], a_day: int, a_task: int, b_day: int, b_task: int,
               a_slot: int = 0, b_slot: int = 0) -> dict:
    """两格对调：以 (day, task_id, slot_index) 定位唯一格子。"""
    def find(day, task, slot):
        for s in slots:
            if s["day"] == day and s["task_id"] == task and int(s.get("slot_index", 0)) == slot:
                return s
        return None
    sa, sb = find(a_day, a_task, a_slot), find(b_day, b_task, b_slot)
    if sa is None or sb is None:
        return {"ok": False, "reason": "slot_missing"}
    if sa["member_id"] == sb["member_id"]:
        return {"ok": False, "reason": "same_assignee"}
    if sa is sb:
        return {"ok": False, "reason": "same_slot"}
    return {
        "ok": True,
        "reason": "",
        "a_member": sa["member_id"],
        "b_member": sb["member_id"],
    }


def apply_swap(slots: list[dict], a_day: int, a_task: int, b_day: int, b_task: int,
               a_slot: int = 0, b_slot: int = 0) -> list[dict]:
    check = swap_legal(slots, a_day, a_task, b_day, b_task, a_slot, b_slot)
    if not check["ok"]:
        raise ValueError(check["reason"])
    out = [dict(s) for s in slots]
    ia = next(i for i, s in enumerate(out)
              if s["day"] == a_day and s["task_id"] == a_task and int(s.get("slot_index", 0)) == a_slot)
    ib = next(i for i, s in enumerate(out)
              if s["day"] == b_day and s["task_id"] == b_task and int(s.get("slot_index", 0)) == b_slot)
    out[ia]["member_id"], out[ib]["member_id"] = out[ib]["member_id"], out[ia]["member_id"]
    return out
