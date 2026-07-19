<script setup lang="ts">
import { computed } from 'vue'
import { radarStats } from '../utils/items'

const props = defineProps<{ stats: Record<string, number> }>()

const size = 240
const cx = size / 2
const cy = size / 2
const rOuter = 92

const entries = computed(() => radarStats(props.stats))

const scale = computed(() => {
  const max = Math.max(0, ...entries.value.map(([, v]) => v))
  return max > 0 ? max : 1
})

function angle(i: number, total: number) {
  return -Math.PI / 2 + (i * Math.PI * 2) / total
}

function radiusFor(v: number): number {
  return (Math.max(0, v) / scale.value) * rOuter
}

const rings = computed(() =>
  [0.25, 0.5, 0.75, 1].map((f) => {
    const r = f * rOuter
    const pts = entries.value
      .map((_, i) => {
        const a = angle(i, entries.value.length)
        return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`
      })
      .join(' ')
    return pts
  }),
)

const axes = computed(() =>
  entries.value.map((_, i) => {
    const a = angle(i, entries.value.length)
    return {
      x2: (cx + rOuter * Math.cos(a)).toFixed(1),
      y2: (cy + rOuter * Math.sin(a)).toFixed(1),
    }
  }),
)

const valuePoints = computed(() =>
  entries.value
    .map(([, v], i) => {
      const a = angle(i, entries.value.length)
      const r = radiusFor(v)
      return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`
    })
    .join(' '),
)

const vertices = computed(() =>
  entries.value.map(([, v], i) => {
    const a = angle(i, entries.value.length)
    const r = radiusFor(v)
    return { cx: (cx + r * Math.cos(a)).toFixed(1), cy: (cy + r * Math.sin(a)).toFixed(1) }
  }),
)

const labels = computed(() =>
  entries.value.map(([label], i) => {
    const a = angle(i, entries.value.length)
    const lx = cx + (rOuter + 18) * Math.cos(a)
    const ly = cy + (rOuter + 18) * Math.sin(a)
    return { label, lx: lx.toFixed(1), ly: ly.toFixed(1) }
  }),
)
</script>

<template>
  <div class="stats-radar-wrap">
    <div class="stats-radar">
      <svg viewBox="0 -18 240 240" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Радар характеристик">
        <polygon v-for="(pts, i) in rings" :key="`ring-${i}`" class="ring" :points="pts" />
        <line
          v-for="(axis, i) in axes"
          :key="`axis-${i}`"
          class="axis"
          :x1="cx"
          :y1="cy"
          :x2="axis.x2"
          :y2="axis.y2"
        />
        <polygon class="area" :points="valuePoints" />
        <circle
          v-for="(v, i) in vertices"
          :key="`v-${i}`"
          class="vertex"
          :cx="v.cx"
          :cy="v.cy"
          r="2.5"
        />
        <text
          v-for="(lb, i) in labels"
          :key="`lbl-${i}`"
          :x="lb.lx"
          :y="lb.ly"
          text-anchor="middle"
          dominant-baseline="middle"
        >{{ lb.label }}</text>
      </svg>
    </div>
  </div>
</template>
