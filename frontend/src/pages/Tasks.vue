<template>
  <div>
    <h1 class="brand">任务</h1>
    <p class="muted">改权重只影响之后新生成的周；下面同时回看所选周生成时落库的快照权重。</p>
    <WeekSwitcher @changed="loadSnapshot" />
    <form @submit.prevent="add" style="margin-top:12px">
      <input v-model="title" placeholder="任务名" />
      <input v-model.number="newWeight" type="number" style="width:110px" placeholder="权重" />
      <button type="submit">添加</button>
    </form>
    <p v-if="err" class="err">{{ err }}</p>
    <ul class="list">
      <li v-for="t in rows" :key="t.id">
        <strong>{{ t.title }}</strong>
        <span class="muted"> · {{ t.data_quality }}</span>
        <div style="display:flex;gap:8px;align-items:center;margin-top:6px;flex-wrap:wrap">
          <label class="muted">现行权重
            <input :value="t.weight" @change="e => save(t, e.target.value)"
                   type="number" style="width:90px;margin:0 6px" />
          </label>
          <span class="chip" :class="{ coral: t.weight <= 0 }">
            {{ t.weight > 0 ? '可入表' : 'weight≤0 不入表' }}
          </span>
          <span v-if="snapMap[t.id] !== undefined" class="chip">
            所选周快照权重 {{ snapMap[t.id] }}
          </span>
          <span v-else-if="hasWeek" class="muted">该周未生成/未入表</span>
        </div>
      </li>
    </ul>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useWeek } from '../week'
import WeekSwitcher from '../components/WeekSwitcher.vue'

const rows = ref([])
const title = ref('')
const newWeight = ref(1)
const snapshot = ref([])
const err = ref('')
const { weekId } = useWeek()
const hasWeek = ref(true)
const snapMap = computed(() => {
  const m = {}
  for (const w of snapshot.value) m[w.task_id] = w.weight
  return m
})
async function load() {
  err.value = ''
  rows.value = await api('/tasks')
  await loadSnapshot()
}
async function loadSnapshot() {
  try {
    const s = await api('/weeks/' + weekId.value + '/task-weights')
    snapshot.value = s.weights || []
    hasWeek.value = true
  } catch { snapshot.value = []; hasWeek.value = false }
}
async function add() {
  err.value = ''
  if (!title.value.trim()) return
  try {
    await api('/tasks', {
      method: 'POST',
      body: JSON.stringify({ title: title.value, weight: newWeight.value || 1 }),
    })
    title.value = ''
    await load()
  } catch (e) { err.value = e.message }
}
async function save(t, v) {
  err.value = ''
  try {
    await api('/tasks/' + t.id, { method: 'PUT', body: JSON.stringify({ weight: Number(v) }) })
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
