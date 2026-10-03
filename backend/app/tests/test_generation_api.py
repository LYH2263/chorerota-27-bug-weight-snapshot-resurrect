"""生成落库 / 快照 / 拒写不改旧表 / 改权重不重切旧周 的接口级测例。"""
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


def _board(client, week=1):
    return client.get(f"/api/weeks/{week}/board").json()


def _snap(client, week=1):
    s = client.get(f"/api/weeks/{week}/task-weights").json()
    return {w["task_id"]: w["weight"] for w in s["weights"]}


def _loads(board):
    return {w["member_id"]: w["slots"] for w in board["workload"]}


def test_generate_persists_cells_and_snapshot(client):
    tids = _task_ids(client)
    r = client.post("/api/weeks/1/generate", json={"days": 7})
    assert r.status_code == 200
    data = r.json()
    # 种子 clean 权重 1+1+2=4/天 → 28 格；28/3 余数 1
    assert data["count"] == 28
    assert data["remainder_policy"] == "lowest_current_load"

    board = _board(client)
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
    assert _snap(client) == {tids["洗碗"]: 1, tids["倒垃圾"]: 1, tids["扫地"]: 2}
    # 成员负荷来自同一份 assignments：10/9/9，差 ≤1
    loads = sorted(w["slots"] for w in board["workload"])
    assert loads == [9, 9, 10]


def test_negative_weight_save_rejected_and_keeps_old_rows(client):
    tids = _task_ids(client)
    ok = client.post("/api/weeks/1/generate", json={"days": 7})
    assert ok.json()["count"] == 28
    before = _board(client)["assignments"]
    before_sig = [(a["day"], a["task_id"], a["slot_index"], a["member_id"],
                   a["weight_snapshot"]) for a in before]

    # 负权保存（PUT/POST）一律拒绝，不落库、不改现行权重
    put = client.put(f"/api/tasks/{tids['洗碗']}", json={"weight": -1})
    assert put.status_code == 400 and put.json()["detail"] == "weight_must_be_positive_int"
    zero = client.put(f"/api/tasks/{tids['洗碗']}", json={"weight": 0})
    assert zero.status_code == 400
    post = client.post("/api/tasks", json={"title": "零权任务", "weight": 0})
    assert post.status_code == 400 and post.json()["detail"] == "weight_must_be_positive_int"

    # 现行权重未变
    live = {t["id"]: t["weight"] for t in client.get("/api/tasks").json()}
    assert live[tids["洗碗"]] == 1
    assert "零权任务" not in {t["title"] for t in client.get("/api/tasks").json()}

    # 已生成周三路（格位归属 / 行内快照 / 负荷）原样
    board = _board(client)
    sig = [(a["day"], a["task_id"], a["slot_index"], a["member_id"], a["weight_snapshot"])
           for a in board["assignments"]]
    assert sig == before_sig
    assert all(a["weight_snapshot"] == 1
               for a in board["assignments"] if a["task_id"] == tids["洗碗"])
    assert sorted(w["slots"] for w in board["workload"]) == [9, 9, 10]
    assert _snap(client) == {tids["洗碗"]: 1, tids["倒垃圾"]: 1, tids["扫地"]: 2}


def test_generation_rejects_non_positive_clean_weight(client):
    """绕过保存接口直插一个 clean 非正权任务：生成兜底整次拒绝，旧表不动。"""
    tids = _task_ids(client)
    client.post("/api/weeks/1/generate", json={"days": 7})
    from app.db import connect
    c = connect()
    cur = c.execute("INSERT INTO tasks(title,weight,data_quality) VALUES (?,?,?)",
                    ("直插零权", 0, "clean"))
    c.commit(); new_tid = cur.lastrowid; c.close()

    r = client.post("/api/weeks/1/generate", json={"days": 7})
    assert r.status_code == 400 and "generation_rejected" in r.json()["detail"]
    board = _board(client)
    assert len(board["assignments"]) == 28
    assert all(a["task_id"] != new_tid for a in board["assignments"])
    # 旧任务快照不变
    assert _snap(client) == {tids["洗碗"]: 1, tids["倒垃圾"]: 1, tids["扫地"]: 2}


def test_changing_weight_does_not_reslice_generated_week(client):
    tids = _task_ids(client)
    members = {m["name"]: m["id"] for m in client.get("/api/members").json()}
    assert client.post("/api/weeks/1/generate", json={"days": 7}).json()["count"] == 28

    before = _board(client)
    before_sig = [(a["day"], a["task_id"], a["slot_index"], a["member_id"])
                  for a in before["assignments"]]
    before_snapshots = [(s["task_id"], s["weight"]) for s in before["snapshots"]]
    before_loads = _loads(before)
    before_cell_count = len(before["assignments"])

    # 现行权重改动：1 → 3（受影响的正是周回看仍钉在 1 的任务）
    r = client.put(f"/api/tasks/{tids['洗碗']}", json={"weight": 3})
    assert r.status_code == 200 and r.json()["weight"] == 3

    # 旧周（week 1）三路必须回到写入钉：格位数/格位归属/行内快照/周快照/负荷全不变
    board = _board(client)
    sig = [(a["day"], a["task_id"], a["slot_index"], a["member_id"])
           for a in board["assignments"]]
    assert sig == before_sig
    assert len(board["assignments"]) == before_cell_count == 28
    assert [(s["task_id"], s["weight"]) for s in board["snapshots"]] == before_snapshots
    assert _snap(client) == {tids["洗碗"]: 1, tids["倒垃圾"]: 1, tids["扫地"]: 2}
    dishes = [a for a in board["assignments"] if a["task_id"] == tids["洗碗"]]
    assert len(dishes) == 7 and all(a["weight_snapshot"] == 1 for a in dishes)
    # 看板占格与成员页当周负荷同一口径，均钉在旧 assignments
    assert _loads(board) == before_loads
    assert sorted(_loads(board).values()) == [9, 9, 10]
    # 改权后该周仍是 ready，未被重切
    week1 = next(w for w in client.get("/api/weeks").json() if w["id"] == 1)
    assert week1["status"] == "ready"

    # 新周生成必须吃新权：1+1+2 中 洗碗 变 3 → 6/天 → 42 格
    nw = client.post("/api/weeks", json={"label": "新周"}).json()
    gen = client.post(f"/api/weeks/{nw['id']}/generate", json={"days": 7})
    assert gen.status_code == 200 and gen.json()["count"] == 42
    nboard = _board(client, nw["id"])
    ndishes = [a for a in nboard["assignments"] if a["task_id"] == tids["洗碗"]]
    assert len(ndishes) == 21 and all(a["weight_snapshot"] == 3 for a in ndishes)
    assert _snap(client, nw["id"]) == {
        tids["洗碗"]: 3, tids["倒垃圾"]: 1, tids["扫地"]: 2}
    # 42/3 整除，每人 14 格，三路一致
    assert sorted(w["slots"] for w in nboard["workload"]) == [14, 14, 14]

    # 等权周在改权前的 round-robin 对照：把权改回全 1 后新生成周，
    # 格位属主必须与改造前逐格 round-robin 同参一致（21 格，成员循环）
    for t in ("洗碗", "扫地"):
        assert client.put(f"/api/tasks/{tids[t]}",
                          json={"weight": 1}).status_code == 200
    ew = client.post("/api/weeks", json={"label": "等权周"}).json()
    assert client.post(f"/api/weeks/{ew['id']}/generate", json={"days": 7}).status_code == 200
    eb = _board(client, ew["id"])
    mids = [members["阿明"], members["小雨"], members["爷爷"]]  # id 升序
    flat = sorted(eb["assignments"], key=lambda a: (a["day"], a["task_id"], a["slot_index"], a["id"]))
    assert len(flat) == 21
    for i, a in enumerate(flat):
        assert a["member_id"] == mids[i % 3]
    assert all(a["weight_snapshot"] == 1 for a in flat)
    assert sorted(w["slots"] for w in eb["workload"]) == [7, 7, 7]


def test_weighted_swap_uses_slot_identity(client):
    tids = _task_ids(client)
    client.post("/api/weeks/1/generate", json={"days": 7})
    b = _board(client)["assignments"]
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
