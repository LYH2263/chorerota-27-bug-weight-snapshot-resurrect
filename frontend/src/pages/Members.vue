<template>
  <div>
    <h1 class="brand">成员</h1>
    <p class="muted">只有活跃 clean 成员参与填人；当周负荷按所选周实际格子统计，与看板同口径。</p>
    <WeekSwitcher @changed="loadWeek" />
    <form @submit.prevent="add" style="margin-top:12px">
      <input v-model="name" placeholder="新成员姓名" />
      <button type="submit">添加</button>
    </form>
    <ul class="list">
      <li v-for="m in rows" :key="m.id">
        <strong>{{ m.name }}</strong>
        <span class="muted"> · {{ m.active ? '在岗' : '停用' }} · {{ m.data_quality }}</span>
        <span v-if="loadMap[m.id] !== undefined" class="chip coral">
          当周 {{ loadMap[m.id] }} 格
        </span>
      </li>
    </ul>
    <p v-if="policy" class="muted">负荷口径：{{ policy }}</p>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useWeek } from '../week'
import WeekSwitcher from '../components/WeekSwitcher.vue'

const rows = ref([])
const workload = ref([])
const policy = ref('')
const name = ref('')
const { weekId } = useWeek()
const loadMap = computed(() => {
  const m = {}
  for (const w of workload.value) m[w.member_id] = w.slots
  return m
})
async function load() {
  rows.value = await api('/members')
  await loadWeek()
}
async function loadWeek() {
  try {
    const b = await api('/weeks/' + weekId.value + '/board')
    workload.value = b.workload || []
    policy.value = b.remainder_policy_label || ''
  } catch { workload.value = []; policy.value = '' }
}
async function add() {
  if (!name.value.trim()) return
  await api('/members', { method: 'POST', body: JSON.stringify({ name: name.value }) })
  name.value = ''; await load()
}
onMounted(load)
</script>
