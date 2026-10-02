<template>
  <div class="week-switch">
    <select :value="weekId" @change="onChange">
      <option v-for="w in weeks" :key="w.id" :value="w.id">
        {{ w.label }}（#{{ w.id }} · {{ w.status }}）
      </option>
    </select>
    <button class="ghost" type="button" @click="add">新建周</button>
  </div>
</template>
<script setup>
import { onMounted } from 'vue'
import { useWeek } from '../week'
const emit = defineEmits(['changed'])
const { weeks, weekId, loadWeeks, selectWeek, addWeek } = useWeek()
async function onChange(e) {
  await selectWeek(Number(e.target.value))
  emit('changed')
}
async function add() {
  await addWeek('新周')
  emit('changed')
}
onMounted(loadWeeks)
</script>
