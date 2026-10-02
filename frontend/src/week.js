import { ref } from 'vue'
import { api } from './api'

// 全应用共享的「当前查看周」：看板占格 / 成员页当周负荷 / 任务页周快照同钉
const weeks = ref([])
const weekId = ref(Number(localStorage.getItem('chorerota.weekId')) || 1)

export function useWeek() {
  async function loadWeeks() {
    weeks.value = await api('/weeks')
    if (!weeks.value.some(w => w.id === weekId.value) && weeks.value.length) {
      await selectWeek(weeks.value[weeks.value.length - 1].id)
    }
  }
  async function selectWeek(id) {
    weekId.value = id
    localStorage.setItem('chorerota.weekId', String(id))
  }
  async function addWeek(label) {
    const w = await api('/weeks', {
      method: 'POST',
      body: JSON.stringify({ label: label || '新周' }),
    })
    await loadWeeks()
    await selectWeek(w.id)
    return w.id
  }
  const currentWeek = () => weeks.value.find(w => w.id === weekId.value)
  return { weeks, weekId, loadWeeks, selectWeek, addWeek, currentWeek }
}
