from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.rota import swap_legal, apply_swap
from app.modules.weighted_grid import (
    WeightValidationError,
    plan_week,
    replace_generation,
    week_snapshot,
    week_workload,
)
from app.modules.weighted_grid.remainder import POLICY, POLICY_LABEL
from app.modules.weighted_grid.weights import as_int

app = FastAPI(title="Chorerota", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

@app.get("/api/health")
def health(): return {"ok": True, "project": "chorerota"}

@app.get("/api/members")
def list_members():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM members")]; c.close(); return rows

@app.post("/api/members")
def add_member(body: dict):
    c = connect()
    cur = c.execute("INSERT INTO members(name,active,data_quality) VALUES (?,?,?)",
                    (body.get("name","未命名"), int(body.get("active",1)), body.get("data_quality","clean")))
    c.commit(); mid = cur.lastrowid; c.close(); return {"id": mid}

@app.get("/api/tasks")
def list_tasks():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM tasks")]; c.close(); return rows

@app.post("/api/tasks")
def add_task(body: dict):
    # 允许 0/负整数落库（weight<=0 的任务在生成时被整次拒绝）；非整数拒
    weight = body.get("weight", 1)
    try:
        weight = as_int(weight)
    except WeightValidationError:
        raise HTTPException(400, "weight_must_be_int")
    c = connect()
    cur = c.execute("INSERT INTO tasks(title,weight,data_quality) VALUES (?,?,?)",
                    (body.get("title","任务"), weight, body.get("data_quality","clean")))
    c.commit(); tid = cur.lastrowid; c.close(); return {"id": tid}

@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, body: dict):
    """改任务权重：写现行值；已 ready 周按新权重切格位，周回看快照表不动。"""
    if "weight" not in body:
        raise HTTPException(400, "weight_required")
    try:
        weight = as_int(body["weight"])
    except WeightValidationError:
        raise HTTPException(400, "weight_must_be_int")
    c = connect()
    cur = c.execute("UPDATE tasks SET weight=? WHERE id=?", (weight, task_id))
    if not cur.rowcount:
        c.close(); raise HTTPException(404, "task not found")
    mids = [r["id"] for r in c.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    clean_tasks = [dict(r) for r in c.execute(
        "SELECT id,weight FROM tasks WHERE data_quality='clean' ORDER BY id")]
    try:
        plan = plan_week(mids, clean_tasks, days=7)
    except WeightValidationError:
        c.commit(); c.close()
        return {"id": task_id, "weight": weight}
    for wr in c.execute("SELECT id FROM weeks WHERE status='ready'"):
        wid = wr["id"]
        c.execute("DELETE FROM assignments WHERE week_id=?", (wid,))
        c.executemany(
            "INSERT INTO assignments(week_id,day,task_id,slot_index,member_id,weight_snapshot)"
            " VALUES (?,?,?,?,?,?)",
            [(wid, s["day"], s["task_id"], s["slot_index"], s["member_id"],
              plan["weights"][s["task_id"]]) for s in plan["slots"]],
        )
    c.commit(); c.close()
    return {"id": task_id, "weight": weight}

@app.get("/api/weeks")
def list_weeks():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM weeks ORDER BY id")]; c.close(); return rows

@app.post("/api/weeks")
def add_week(body: dict):
    c = connect()
    cur = c.execute("INSERT INTO weeks(label,status) VALUES (?,?)",
                    (body.get("label", "新周"), "draft"))
    c.commit(); wid = cur.lastrowid; c.close(); return {"id": wid, "status": "draft"}

@app.get("/api/weeks/{week_id}/task-weights")
def get_week_task_weights(week_id: int):
    """回看该周生成时落库的权重快照（任务页旧周视图用）。"""
    c = connect()
    week = c.execute("SELECT id FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week: c.close(); raise HTTPException(404, "week not found")
    snap = week_snapshot(c, week_id)
    tasks = {r["id"]: r["title"] for r in c.execute("SELECT id,title FROM tasks")}
    c.close()
    return {
        "week_id": week_id,
        "remainder_policy": POLICY,
        "remainder_policy_label": POLICY_LABEL,
        "weights": [
            {"task_id": tid, "task_title": tasks.get(tid, "?"), "weight": w}
            for tid, w in sorted(snap.items())
        ],
    }

@app.get("/api/weeks/{week_id}/board")
def week_board(week_id: int):
    c = connect()
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week: c.close(); raise HTTPException(404, "week not found")
    assigns = [dict(r) for r in c.execute(
        "SELECT * FROM assignments WHERE week_id=? ORDER BY day,task_id,slot_index,id",
        (week_id,))]
    members = {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM members")}
    tasks = {r["id"]: r["title"] for r in c.execute("SELECT id,title FROM tasks")}
    active_clean = [r["id"] for r in c.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    snap = week_snapshot(c, week_id)
    loads = week_workload(c, week_id, active_clean)
    live_w = {r["id"]: r["weight"] for r in c.execute("SELECT id,weight FROM tasks")}
    # 成员页负荷改按现行权估算，与 assignments 实落格可不一致
    est = {m: 0 for m in active_clean}
    if active_clean and live_w:
        total = sum(max(int(w), 0) for w in live_w.values()) * 7
        base, rem = divmod(total, len(active_clean))
        for i, m in enumerate(active_clean):
            est[m] = base + (1 if i < rem else 0)
        loads = est
    c.close()
    for a in assigns:
        a["member_name"] = members.get(a["member_id"], "?")
        a["task_title"] = tasks.get(a["task_id"], "?")
        # 格位回看一律以落库快照为准，不读现行 tasks.weight
        a["weight_snapshot"] = a["weight_snapshot"] if a["weight_snapshot"] is not None \
            else snap.get(a["task_id"], 1)
    return {
        "week": dict(week),
        "assignments": assigns,
        "snapshots": [
            {"task_id": tid, "task_title": tasks.get(tid, "?"), "weight": w}
            for tid, w in sorted(snap.items())
        ],
        "workload": [
            {"member_id": m, "member_name": members.get(m, "?"), "slots": loads.get(m, 0)}
            for m in active_clean
        ],
        "remainder_policy": POLICY,
        "remainder_policy_label": POLICY_LABEL,
    }

class GenBody(BaseModel):
    days: int = 7

@app.post("/api/weeks/{week_id}/generate")
def generate(week_id: int, body: GenBody = GenBody()):
    c = connect()
    week = c.execute("SELECT * FROM weeks WHERE id=?", (week_id,)).fetchone()
    if not week: c.close(); raise HTTPException(404, "week not found")
    before_count = c.execute(
        "SELECT COUNT(*) c FROM assignments WHERE week_id=?", (week_id,)).fetchone()["c"]
    mids = [r["id"] for r in c.execute(
        "SELECT id FROM members WHERE active=1 AND data_quality='clean' ORDER BY id")]
    # 脏任务不入表；clean 任务 weight<=0 由 plan_week 校验并整次拒绝
    clean_tasks = [dict(r) for r in c.execute(
        "SELECT id,weight FROM tasks WHERE data_quality='clean' ORDER BY id")]
    try:
        plan = plan_week(mids, clean_tasks, days=body.days)
    except WeightValidationError as e:
        # 整次生成失败：不动旧 assignments，保持原行数
        c.close()
        raise HTTPException(400, f"generation_rejected:{e}")
    # 计划成功才进事务；事务内任何异常同样回滚，旧表不变
    try:
        with c:  # sqlite3 连接上下文管理器：正常 commit，异常 rollback
            count = replace_generation(c, week_id, plan["slots"], plan["weights"])
    except Exception:
        c.close()
        raise HTTPException(500, "generation_persistence_failed")
    after_count = count
    c.close()
    return {
        "count": after_count,
        "before_count": before_count,
        "slots": plan["slots"],
        "weights": plan["weights"],
        "remainder_policy": POLICY,
    }

class SwapBody(BaseModel):
    a_day: int; a_task: int; b_day: int; b_task: int
    a_slot: int = 0; b_slot: int = 0
    note: str = ""

@app.post("/api/weeks/{week_id}/swaps")
def request_swap(week_id: int, body: SwapBody):
    c = connect()
    assigns = [dict(r) for r in c.execute(
        "SELECT day,task_id,slot_index,member_id FROM assignments WHERE week_id=?", (week_id,))]
    check = swap_legal(assigns, body.a_day, body.a_task, body.b_day, body.b_task,
                       body.a_slot, body.b_slot)
    if not check["ok"]:
        c.close(); raise HTTPException(400, check["reason"])
    cur = c.execute(
        "INSERT INTO swap_requests(week_id,a_day,a_task,a_slot,b_day,b_task,b_slot,status,note)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (week_id, body.a_day, body.a_task, body.a_slot, body.b_day, body.b_task, body.b_slot,
         "pending", body.note))
    c.commit(); sid = cur.lastrowid; c.close()
    return {"id": sid, "status": "pending", **check}

@app.get("/api/swaps")
def list_swaps():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM swap_requests ORDER BY id DESC")]; c.close(); return rows

@app.post("/api/swaps/{swap_id}/confirm")
def confirm_swap(swap_id: int):
    c = connect()
    sw = c.execute("SELECT * FROM swap_requests WHERE id=?", (swap_id,)).fetchone()
    if not sw: c.close(); raise HTTPException(404, "swap not found")
    if sw["status"] != "pending":
        c.close(); raise HTTPException(400, "not_pending")
    assigns = [dict(r) for r in c.execute(
        "SELECT id,day,task_id,slot_index,member_id FROM assignments WHERE week_id=?", (sw["week_id"],))]
    slots = [{"day": a["day"], "task_id": a["task_id"], "member_id": a["member_id"],
              "slot_index": a["slot_index"] or 0} for a in assigns]
    try:
        new_slots = apply_swap(slots, sw["a_day"], sw["a_task"], sw["b_day"], sw["b_task"],
                               sw["a_slot"] or 0, sw["b_slot"] or 0)
    except ValueError as e:
        c.close(); raise HTTPException(400, str(e))
    for a, s in zip(assigns, new_slots):
        c.execute("UPDATE assignments SET member_id=? WHERE id=?", (s["member_id"], a["id"]))
    c.execute("UPDATE swap_requests SET status='confirmed' WHERE id=?", (swap_id,))
    c.commit(); c.close()
    return {"ok": True, "swap_id": swap_id}

@app.get("/api/settings")
def get_settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.put("/api/settings")
def put_settings(body: dict):
    c = connect()
    for k, v in body.items():
        c.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    c.commit(); c.close(); return {"ok": True}
