"""余数策略（已拍板口径）：余数格 → 当前负荷最低成员优先。

总格数不能被人数整除时：先按 round-robin 铺满 q*人数 个基础格
（q = 总格数 // 人数，每人恰好 q 格），余下 r 格逐格给当前总负荷
最低的成员；同负荷时按成员 id 升序兜底。最终任意两人负荷差 ≤ 1。

看板占格与成员页当周负荷都必须以本策略产出的同一份 slots 计数。
"""

POLICY = "lowest_current_load"
POLICY_LABEL = "余数格→当前负荷最低成员优先（同负荷按成员id升序）"


def assign_with_remainder(cells: list[dict], member_ids: list[int]) -> list[dict]:
    """给展平的格子填成员。cells 为 [{day, task_id, slot_index}]。"""
    if not cells or not member_ids:
        return []
    mids = sorted(member_ids)
    n = len(mids)
    slots = [dict(c) for c in cells]
    total = len(slots)
    base_n = total - (total % n)  # round-robin 基段长度

    # 基段 round-robin：与改造前 build_week_slots 逐格一致
    for i in range(base_n):
        slots[i]["member_id"] = mids[i % n]

    # 余数段：每格给当前负荷最低者；基段后每人都是 base_n//n 格
    loads = {m: base_n // n for m in mids}
    for s in slots[base_n:]:
        chosen = min(mids, key=lambda m: (loads[m], m))
        s["member_id"] = chosen
        loads[chosen] += 1
    return slots
