<script setup lang="ts">
import type { Achievement } from '../api/client'

defineProps<{ achievements: Achievement[] }>()

const kindLabels: Record<Achievement['kind'], string> = {
  hidden_skill: 'Скрытые навыки',
  story_boss: 'Сюжетные боссы',
  secret_echo: 'Особые',
}

function groupByKind(achievements: Achievement[]): Array<{ kind: Achievement['kind']; items: Achievement[] }> {
  const order: Achievement['kind'][] = ['hidden_skill', 'story_boss', 'secret_echo']
  const groups = new Map<Achievement['kind'], Achievement[]>()
  for (const a of achievements) {
    const list = groups.get(a.kind) ?? []
    list.push(a)
    groups.set(a.kind, list)
  }
  return order
    .filter((k) => groups.has(k))
    .map((k) => ({ kind: k, items: groups.get(k)! }))
}

function formatDate(iso?: string): string | null {
  if (!iso) return null
  return iso.slice(0, 10)
}
</script>

<template>
  <div v-if="!achievements.length">
    <p style="color: var(--muted)">Достижений пока нет</p>
  </div>
  <div v-else>
    <section v-for="group in groupByKind(achievements)" :key="group.kind" style="margin-bottom: 1.25rem">
      <h3 style="font-size: 0.9rem; color: var(--muted); margin-bottom: 0.5rem">{{ kindLabels[group.kind] }}</h3>
      <div class="achievement-grid">
        <div v-for="a in group.items" :key="`${a.kind}-${a.id}`" class="achievement-card">
          <span v-if="a.icon" class="achievement-icon">{{ a.icon }}</span>
          <span v-else class="achievement-icon">🏆</span>
          <div class="achievement-body">
            <div class="achievement-name">{{ a.name }}</div>
            <div v-if="a.level" class="achievement-meta">Уровень {{ a.level }}/{{ a.max_level ?? 5 }}</div>
            <div v-else-if="a.act != null && a.plus_tier != null" class="achievement-meta">
              Акт {{ a.act }}, +{{ a.plus_tier }}
            </div>
            <div v-if="formatDate(a.earned_at)" class="achievement-date">{{ formatDate(a.earned_at) }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
