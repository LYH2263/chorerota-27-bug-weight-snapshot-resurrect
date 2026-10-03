# Chorerota · 家庭值日轮转

底座：成员+任务 → 加权 round-robin 生成周表 → 申请对调 → 确认改表。

## 加权占格口径（唯一口径）

- 仅 `data_quality='clean'` 且权重为正整数的任务入表，按权重在每日占多格
  （weight=2 一天两格，格位身份为 `slot_index`）；weight≤0 或脏任务不入表。
  权重**保存即校验**：POST/PUT `/api/tasks` 收到 0、负数或非整数一律 400，
  不落库；生成时再兜底，万一存在 clean 且 weight≤0 的行则**整次生成失败**，
  `assignments` 保持原行数。
- 成员仅取活跃 clean 集合，按「日→任务(id)→格位」展平后填人：基段
  round-robin；总格数不能被人数整除时，余数格走**当前负荷最低成员优先**
  （同负荷按成员 id 升序），最终任意两人负荷差 ≤1。
- weight 全为 1 时与改造前逐格一致。
- 生成时把各任务**权重快照**（`week_task_weights` + `assignments.weight_snapshot`）
  与格子同一事务落库；之后改任务权重只影响新周，旧周看板/任务页回看一律读快照，
  不按新权重重切。
- 看板占格与成员页当周负荷都来自同一份 assignments（board 接口返回
  `workload` 与 `remainder_policy_label`）。

口径分模块实现：`app/modules/weighted_grid/`（`weights.py` 权重口径 /
`remainder.py` 余数策略 / `planner.py` 编排 / `persistence.py` 落库）。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5100 |
| API | 10100 |

```bash
docker compose up --build
pytest backend/app/tests
```

种子含 clean/dirty。0-1 空桩：`streak_badge` / `skip_week` / `chore_photo`。
