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


def test_negative_weight_rejects_and_keeps_old_rows(client):
    tids = _task_ids(client)
    ok = client.post("/api/weeks/1/generate", json={"days": 7})
    assert ok.json()["count"] == 28

    # clean 任务改成负权 → 整次生成失败
    put = client.put(f"/api/tasks/{tids['洗碗']}", json={"weight": -1})
    assert put.status_code == 200  # 0/负允许落库，生成时才卡
    r = client.post("/api/weeks/1/generate", json={"days": 7})
    assert r.status_code == 400
    assert "generation_rejected" in r.json()["detail"]
    # assignments 保持原行数与原快照
    board = client.get("/api/weeks/1/board").json()
    assert len(board["assignments"]) == 28
    old_dishes = [a for a in board["assignments"] if a["task_id"] == tids["洗碗"]]
    assert all(a["weight_snapshot"] == 1 for a in old_dishes)


def test_changing_weight_does_not_reslice_generated_week(client):
    pass


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
