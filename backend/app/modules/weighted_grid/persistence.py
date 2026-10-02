"""落库：权重快照与格子同一事务写入。

- assignments 每行带 weight_snapshot（生成时该任务权重）与 slot_index；
- week_task_weights 存该周 {task_id: weight} 快照，任务页回看旧周读它；
- replace_generation 仅在计划成功后调用，整事务替换，失败不影响旧表。
"""


def replace_generation(conn, week_id: int, slots: list[dict], weights: dict[int, int]) -> int:
    """单事务：删旧格+旧快照 → 写新格+新快照 → 置 ready。返回写入格数。"""
    cur = conn.cursor()
    cur.execute("DELETE FROM assignments WHERE week_id=?", (week_id,))
    cur.execute("DELETE FROM week_task_weights WHERE week_id=?", (week_id,))
    cur.executemany(
        "INSERT INTO week_task_weights(week_id,task_id,weight) VALUES (?,?,?)",
        [(week_id, tid, w) for tid, w in sorted(weights.items())],
    )
    cur.executemany(
        "INSERT INTO assignments(week_id,day,task_id,slot_index,member_id,weight_snapshot)"
        " VALUES (?,?,?,?,?,?)",
        [(week_id, s["day"], s["task_id"], s["slot_index"], s["member_id"],
          weights[s["task_id"]]) for s in slots],
    )
    cur.execute("UPDATE weeks SET status='ready' WHERE id=?", (week_id,))
    return len(slots)


def week_snapshot(conn, week_id: int) -> dict[int, int]:
    """读该周落库的权重快照（任务页回看旧周用，不读 tasks 现行权重）。"""
    rows = conn.execute(
        "SELECT task_id,weight FROM week_task_weights WHERE week_id=?", (week_id,))
    return {r["task_id"]: r["weight"] for r in rows}


def week_workload(conn, week_id: int, member_ids: list[int] | None = None) -> dict[int, int]:
    """按该周 assignments 实落格子统计负荷（看板/成员页同一口径）。"""
    if member_ids is None:
        member_ids = [r["id"] for r in conn.execute("SELECT id FROM members")]
    loads = {m: 0 for m in member_ids}
    for r in conn.execute(
            "SELECT member_id, COUNT(*) c FROM assignments WHERE week_id=? GROUP BY member_id",
            (week_id,)):
        loads[r["member_id"]] = r["c"]
    return loads
