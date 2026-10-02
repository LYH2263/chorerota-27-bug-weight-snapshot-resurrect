<template>
  <div>
    <h1 class="brand">本周看板</h1>
    <p class="muted">加权占格：clean 正权任务按权重每日占多格 · round-robin 基段 + 余数最低负荷</p>
    <WeekSwitcher @changed="load" />
    <div style="display:flex;gap:8px;margin:12px 0;flex-wrap:wrap">
      <button @click="generate">生成周表</button>
      <button class="ghost" @click="load">刷新</button>
      <span v-if="policy" class="muted">口径：{{ policy }}</span>
    </div>
    <p v-if="err" class="err">{{ err }}</p>

    <section v-if="workload.length" class="week-card" style="margin-bottom:12px">
      <header>当周负荷（格数，与占格同口径）</header>
      <span v-for="w in workload" :key="w.member_id" class="chip">
        {{ w.member_name }} · {{ w.slots }}格
      </span>
    </section>

    <div class="week-grid">
      <article v-for="d in days" :key="d" class="week-card">
        <header>Day {{ d + 1 }}</header>
        <div v-for="a in byDay(d)" :key="a.id" class="cell-row">
          <span class="chip">{{ a.task_title }}<i class="slot-no">#{{ a.slot_index + 1 }}</i></span>
          <span class="chip coral">{{ a.member_name }}</span>
        </div>
        <p v-if="!byDay(d).length" class="muted">空</p>
      </article>
    </div>

    <section v-if="snapshots.length" style="margin-top:12px">
      <header class="muted">本周生成时权重快照（改权重不重切本周）</header>
      <span v-for="s in snapshots" :key="s.task_id" class="chip">
        {{ s.task_title }} · 权重 {{ s.weight }}
      </span>
    </section>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useWeek } from '../week'
import WeekSwitcher from '../components/WeekSwitcher.vue'

const assigns = ref([])
const workload = ref([])
const snapshots = ref([])
const policy = ref('')
const days = [0,1,2,3,4,5,6]
const err = ref('')
const { weekId } = useWeek()

function byDay(d) { return assigns.value.filter(a => a.day === d) }

async function load() {
  err.value = ''
  try {
    const b = await api('/weeks/' + weekId.value + '/board')
    assigns.value = b.assignments || []
    workload.value = b.workload || []
    snapshots.value = b.snapshots || []
    policy.value = b.remainder_policy_label || ''
  } catch (e) { err.value = e.message }
}
async function generate() {
  err.value = ''
  try {
    await api('/weeks/' + weekId.value + '/generate', { method: 'POST', body: '{}' })
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
