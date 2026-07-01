<script setup>
import { computed, ref } from "vue";

const monsterHp = ref(0);
const monsterMaxHp = ref(1);
const waifuHp = ref(0);
const waifuMaxHp = ref(1);
const hpKnown = ref(true);

const monsterBarPct = computed(() =>
  hpKnown.value
    ? Math.max(0, Math.min(100, (monsterHp.value / Math.max(1, monsterMaxHp.value)) * 100))
    : 100
);
const waifuPct = computed(() =>
  Math.max(0, Math.min(100, (waifuHp.value / Math.max(1, waifuMaxHp.value)) * 100))
);
const monsterHpLabel = computed(() =>
  hpKnown.value ? `${monsterHp.value} / ${monsterMaxHp.value}` : "??? / ???"
);
const waifuHpLabel = computed(() => `${waifuHp.value} / ${waifuMaxHp.value}`);

function applyPayload(payload) {
  if (!payload || typeof payload !== "object") return;
  if (payload.monster_hp != null) monsterHp.value = Number(payload.monster_hp) || 0;
  if (payload.monster_max_hp != null) monsterMaxHp.value = Math.max(1, Number(payload.monster_max_hp) || 1);
  if (payload.waifu_current_hp != null) waifuHp.value = Number(payload.waifu_current_hp) || 0;
  if (payload.waifu_max_hp != null) waifuMaxHp.value = Math.max(1, Number(payload.waifu_max_hp) || 1);
}

defineExpose({ applyPayload, setBaseline });
function setBaseline({ monster, waifu }) {
  if (monster) {
    monsterHp.value = Number(monster.current_hp) || 0;
    monsterMaxHp.value = Math.max(1, Number(monster.max_hp) || 1);
    hpKnown.value = monster.hp_known !== false;
  }
  if (waifu) {
    waifuHp.value = Number(waifu.current_hp) || 0;
    waifuMaxHp.value = Math.max(1, Number(waifu.max_hp) || 1);
  }
}
</script>

<template>
  <div class="combat-island">
    <div class="combat-island-row">
      <span class="combat-island-icon" aria-label="HP монстра" title="HP монстра">👹</span>
      <div class="combat-island-bar">
        <div
          class="combat-island-fill combat-island-fill--monster"
          :class="{ 'combat-island-fill--unknown': !hpKnown }"
          :style="{ width: monsterBarPct + '%' }"
        />
      </div>
      <span class="combat-island-values">{{ monsterHpLabel }}</span>
    </div>
    <div class="combat-island-row">
      <span class="combat-island-icon" aria-label="HP вайфу" title="HP вайфу">🌸</span>
      <div class="combat-island-bar">
        <div class="combat-island-fill combat-island-fill--waifu" :style="{ width: waifuPct + '%' }" />
      </div>
      <span class="combat-island-values">{{ waifuHpLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.combat-island {
  position: relative;
  width: 100%;
  margin: 6px 0 0;
  padding: 0;
  background: none;
  border: none;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.combat-island-row {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 6px;
  align-items: center;
}
.combat-island-icon {
  font-size: 0.7rem;
  line-height: 1;
  text-align: center;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85);
}
.combat-island-bar {
  height: 6px;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
  overflow: hidden;
}
.combat-island-fill {
  height: 100%;
  transition: width 0.12s ease-out;
}
.combat-island-fill--monster {
  background: linear-gradient(90deg, #dc2626, #f87171);
}
.combat-island-fill--monster.combat-island-fill--unknown {
  background: linear-gradient(90deg, #57534e, #78716c);
}
.combat-island-fill--waifu {
  background: linear-gradient(90deg, #16a34a, #4ade80);
}
.combat-island-values {
  font-size: 0.62rem;
  color: #fff;
  min-width: 4rem;
  text-align: right;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9);
  white-space: nowrap;
}
</style>
