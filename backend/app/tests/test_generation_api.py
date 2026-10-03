"""生成落库 / 快照 / 拒写不改旧表 / 改权重不重切旧周 的接口级测例。"""
import os
import pytest

# 在导入 app 之前指定临时数据目录（db_path 在调用时读取环境变量）
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _task_ids(client):
    return {t["title"]: t["id"] for t in client.get("/api/tasks").json()}


def test_generate_persists_cells_and_snapshot(client):
    tids = _task_ids(client)
    r = client.post("/api/weeks/1/generate", json={"days": 7})
    assert r.status_code == 200
    data = r.json()
    # 种子 clean 权重 1+1+2=4/天 → 28 格；28/3 余数 1
    assert data["count"] == 28
    assert data["remainder_policy"] == "lowest_current_load"

    board = client.get("/api/weeks/1/board").json()
    assigns = board["assignments"]
    assert len(assigns) == 28
    # 每格带生成时权重快照
    sweep = [a for a in assigns if a["task_id"] == tids["扫地"]]
    assert len(sweep) == 14 and all(a["weight_snapshot"] == 2 for a in sweep)
    # 每日 weight=2 任务有 slot_index 0/1 两个格位
    day0 = [(a["task_id"], a["slot_index"]) for a in assigns if a["day"] == 0]
    assert day0.count((tids["扫地"], 0)) == 1
    assert day0.count((tids["扫地"], 1)) == 1
    # 脏任务（负权重且 dirty）从不入表
    assert all(a["task_id"] != tids["负权重任务"] for a in assigns)
    # 快照表同钉
    snap = client.get("/api/weeks/1/task-weights").json()
    weights = {w["task_id"]: w["weight"] for w in snap["weights"]}
    assert weights == {tids["洗碗"]: 1, tids["倒垃圾"]: 1, tids["扫地"]: 2}
    # 成员负荷来自同一份 assignments：10/9/9，差 ≤1
    loads = sorted(w["slots"] for w in board["workload"])
    assert loads == [9, 9, 10]


def test_negative_weight_save_rejected_and_keeps_old_rows(client):
    tids = _task_ids(client)
    ok = client.post("/api/weeks/1/generate", json={"days": 7})
    assert ok.json()["count"] == 28

    # 负权：保存即拒（PUT/POST 一致），不动旧表
    put = client.put(f"/api/tasks/{tids['洗碗']}", json={"weight": -1})
    assert put.status_code == 400
    assert put.json()["detail"] == "weight_must_not_be_negative"
    post = client.post("/api/tasks", json={"title": "坏任务", "weight": -3})
    assert post.status_code == 400
    # 现行权重未被改写
    dishes = next(t for t in client.get("/api/tasks").json() if t["id"] == tids["洗碗"])
    assert dishes["weight"] == 1
    board = client.get("/api/weeks/1/board").json()
    assert len(board["assignments"]) == 28
    old_dishes = [a for a in board["assignments"] if a["task_id"] == tids["洗碗"]]
    assert all(a["weight_snapshot"] == 1 for a in old_dishes)


def test_zero_weight_saves_but_rejects_generation(client):
    tids = _task_ids(client)
    assert client.post("/api/weeks/1/generate", json={"days": 7}).json()["count"] == 28

    # 0 允许保存（不入表口径），但 clean 任务 weight<=0 → 整次生成失败，旧表不变
    assert client.put(f"/api/tasks/{tids['洗碗']}", json={"weight": 0}).status_code == 200
    r = client.post("/api/weeks/1/generate", json={"days": 7})
    assert r.status_code == 400
    assert "generation_rejected" in r.json()["detail"]
    board = client.get("/api/weeks/1/board").json()
    assert len(board["assignments"]) == 28
    old_dishes = [a for a in board["assignments"] if a["task_id"] == tids["洗碗"]]
    assert all(a["weight_snapshot"] == 1 for a in old_dishes)


def test_changing_weight_does_not_reslice_generated_week(client):
    tids = _task_ids(client)
    assert client.post("/api/weeks/1/generate", json={"days": 7}).status_code == 200
    before = client.get("/api/weeks/1/board").json()
    before_cells = [(a["day"], a["task_id"], a["slot_index"], a["member_id"],
                     a["weight_snapshot"]) for a in before["assignments"]]
    before_loads = {w["member_id"]: w["slots"] for w in before["workload"]}
    before_snap = {w["task_id"]: w["weight"]
                   for w in client.get("/api/weeks/1/task-weights").json()["weights"]}

    # 事后只改现行任务权重：旧周格数/格位归属/负荷/快照三路全部钉在写入值
    assert client.put(f"/api/tasks/{tids['扫地']}", json={"weight": 5}).status_code == 200
    after = client.get("/api/weeks/1/board").json()
    after_cells = [(a["day"], a["task_id"], a["slot_index"], a["member_id"],
                    a["weight_snapshot"]) for a in after["assignments"]]
    assert after_cells == before_cells
    assert {w["member_id"]: w["slots"] for w in after["workload"]} == before_loads
    after_snap = {w["task_id"]: w["weight"]
                  for w in client.get("/api/weeks/1/task-weights").json()["weights"]}
    assert after_snap == before_snap
    # 看板占格总数与成员负荷汇总同钉
    assert sum(w["slots"] for w in after["workload"]) == len(after_cells) == 28

    # 新周生成吃新权：扫地权重 5 → 7*(1+1+5)=49 格
    new_week = client.post("/api/weeks", json={"label": "第13周"}).json()
    gen = client.post(f"/api/weeks/{new_week['id']}/generate", json={"days": 7})
    assert gen.status_code == 200 and gen.json()["count"] == 49
    nb = client.get(f"/api/weeks/{new_week['id']}/board").json()
    sweep = [a for a in nb["assignments"] if a["task_id"] == tids["扫地"]]
    assert len(sweep) == 35 and all(a["weight_snapshot"] == 5 for a in sweep)
    nsnap = {w["task_id"]: w["weight"]
             for w in client.get(f"/api/weeks/{new_week['id']}/task-weights").json()["weights"]}
    assert nsnap[tids["扫地"]] == 5
    assert sum(w["slots"] for w in nb["workload"]) == 49


def test_equal_weight_week_matches_legacy_layout(client):
    """等权周与改造前 build_week_slots 同参逐格一致（含余数 10/9/9）。"""
    from app.engines.rota import build_week_slots
    tids = _task_ids(client)
    # 全部 clean 任务改为等权 1
    for t in ("洗碗", "倒垃圾", "扫地"):
        assert client.put(f"/api/tasks/{tids[t]}", json={"weight": 1}).status_code == 200
    assert client.post("/api/weeks/1/generate", json={"days": 7}).status_code == 200
    board = client.get("/api/weeks/1/board").json()
    mids = [w["member_id"] for w in board["workload"]]
    legacy = build_week_slots(mids, [tids["洗碗"], tids["倒垃圾"], tids["扫地"]], days=7)
    got = [(a["day"], a["task_id"], a["slot_index"], a["member_id"])
           for a in board["assignments"]]
    want = [(s["day"], s["task_id"], s.get("slot_index", 0), s["member_id"]) for s in legacy]
    assert got == want
    assert sorted(w["slots"] for w in board["workload"]) == [7, 7, 7]


def test_weighted_swap_uses_slot_identity(client):
    tids = _task_ids(client)
    client.post("/api/weeks/1/generate", json={"days": 7})
    b = client.get("/api/weeks/1/board").json()["assignments"]
    # 找两个不同属主的格（扫地同日两格可能分属不同人）
    a = next(a for a in b if a["task_id"] == tids["扫地"] and a["day"] == 0 and a["slot_index"] == 0)
    target = next(x for x in b if x["member_id"] != a["member_id"])
    r = client.post("/api/weeks/1/swaps", json={
        "a_day": a["day"], "a_task": a["task_id"], "a_slot": a["slot_index"],
        "b_day": target["day"], "b_task": target["task_id"], "b_slot": target["slot_index"]})
    assert r.status_code == 200
    assert r.json()["a_member"] == a["member_id"]
    # 缺 slot 的同日同任务重复格不会撞格
    miss = client.post("/api/weeks/1/swaps", json={
        "a_day": 0, "a_task": tids["扫地"], "a_slot": 9,
        "b_day": 1, "b_task": tids["扫地"], "b_slot": 0})
    assert miss.status_code == 400 and miss.json()["detail"] == "slot_missing"
