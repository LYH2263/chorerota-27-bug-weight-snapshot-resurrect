<template>
  <div>
    <h1 class="brand">对调</h1>
    <p class="muted">先生成周表，再填写两格对调（day + task_id + 格位#，加权任务同日多格靠格位区分）</p>
    <WeekSwitcher @changed="load" />
    <div class="week-card" style="margin:12px 0">
      <div class="swap-grid">
        <label>A day <input type="number" v-model.number="form.a_day" /></label>
        <label>A task_id <input type="number" v-model.number="form.a_task" /></label>
        <label>A 格位# <input type="number" v-model.number="form.a_slot" /></label>
        <label>B day <input type="number" v-model.number="form.b_day" /></label>
        <label>B task_id <input type="number" v-model.number="form.b_task" /></label>
        <label>B 格位# <input type="number" v-model.number="form.b_slot" /></label>
      </div>
      <button @click="request">申请对调</button>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <ul class="list">
      <li v-for="s in rows" :key="s.id">
        #{{ s.id }} D{{ s.a_day }}/T{{ s.a_task }}/#{{ (s.a_slot ?? 0) + 1 }}
        ↔ D{{ s.b_day }}/T{{ s.b_task }}/#{{ (s.b_slot ?? 0) + 1 }}
        <span class="chip" :class="{ coral: s.status==='pending' }">{{ s.status }}</span>
        <button v-if="s.status==='pending'" style="margin-left:8px" @click="confirm(s.id)">确认改表</button>
      </li>
    </ul>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useWeek } from '../week'
import WeekSwitcher from '../components/WeekSwitcher.vue'

const rows = ref([])
const err = ref('')
const form = ref({ a_day: 0, a_task: 1, a_slot: 1, b_day: 1, b_task: 1, b_slot: 1 })
const { weekId } = useWeek()
async function load() { rows.value = await api('/swaps') }
async function request() {
  err.value = ''
  try {
    const body = {
      a_day: form.value.a_day, a_task: form.value.a_task,
      a_slot: Math.max(0, (form.value.a_slot || 1) - 1),
      b_day: form.value.b_day, b_task: form.value.b_task,
      b_slot: Math.max(0, (form.value.b_slot || 1) - 1),
    }
    await api('/weeks/' + weekId.value + '/swaps', { method: 'POST', body: JSON.stringify(body) })
    await load()
  } catch (e) { err.value = e.message }
}
async function confirm(id) {
  err.value = ''
  try { await api('/swaps/' + id, { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
onMounted(load)
</script>
