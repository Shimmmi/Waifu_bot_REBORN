<script setup>
import { computed, ref } from "vue";

const monsterHp = ref(0);
const monsterMaxHp = ref(1);
const waifuHp = ref(0);
const waifuMaxHp = ref(1);
const hpKnown = ref(true);
const lastDamage = ref(null);
const lastCrit = ref(false);
const hitFlash = ref(false);
const floatDamage = ref(null);

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

function applyPayload(payload) {
  if (!payload || typeof payload !== "object") return;
  if (payload.monster_hp != null) monsterHp.value = Number(payload.monster_hp) || 0;
  if (payload.monster_max_hp != null) monsterMaxHp.value = Math.max(1, Number(payload.monster_max_hp) || 1);
  if (payload.waifu_current_hp != null) waifuHp.value = Number(payload.waifu_current_hp) || 0;
  if (payload.waifu_max_hp != null) waifuMaxHp.value = Math.max(1, Number(payload.waifu_max_hp) || 1);
  if (payload.damage != null) {
    lastDamage.value = Number(payload.damage);
    lastCrit.value = payload.is_crit === true;
    if (lastDamage.value > 0 && !payload.monster_dodged) {
      hitFlash.value = false;
      requestAnimationFrame(() => {
        hitFlash.value = true;
        floatDamage.value = lastDamage.value;
        setTimeout(() => {
          hitFlash.value = false;
          floatDamage.value = null;
        }, 900);
      });
    }
  }
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
  lastDamage.value = null;
  lastCrit.value = false;
}
</script>

<template>
  <div class="combat-island">
    <div class="combat-island-bars">
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
        <span class="combat-island-values">{{ waifuHp }} / {{ waifuMaxHp }}</span>
      </div>
    </div>
    <div v-if="lastDamage != null" class="combat-island-meta">
      Удар: <strong>{{ lastDamage }}</strong>
      <span v-if="lastCrit" class="combat-island-crit">★</span>
    </div>
    <div v-if="floatDamage != null" class="combat-island-float" :class="{ 'combat-island-float--crit': lastCrit }">
      -{{ floatDamage }}
    </div>
    <div v-if="hitFlash" class="combat-island-flash" />
  </div>
</template>

<style scoped>
.combat-island {
  position: relative;
  margin: 6px 0 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(251, 191, 36, 0.2);
}
.combat-island-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}
.combat-island-row:last-child {
  margin-bottom: 0;
}
.combat-island-icon {
  font-size: 0.85rem;
  line-height: 1;
  text-align: center;
}
.combat-island-bar {
  height: 8px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 4px;
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
  font-size: 0.7rem;
  color: #e8dcc8;
  min-width: 4.5rem;
  text-align: right;
}
.combat-island-meta {
  font-size: 0.75rem;
  color: #d6d3d1;
  margin-top: 4px;
}
.combat-island-crit {
  color: #fbbf24;
  margin-left: 4px;
}
.combat-island-float {
  position: absolute;
  top: 20%;
  left: 50%;
  transform: translateX(-50%);
  font-weight: 800;
  font-size: 1.1rem;
  color: #f87171;
  pointer-events: none;
  animation: combat-float 0.85s ease-out forwards;
}
.combat-island-float--crit {
  color: #fbbf24;
  font-size: 1.25rem;
}
.combat-island-flash {
  position: absolute;
  inset: 0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.12);
  animation: combat-flash 0.35s ease-out;
  pointer-events: none;
}
@keyframes combat-float {
  from {
    opacity: 1;
    transform: translate(-50%, 0);
  }
  to {
    opacity: 0;
    transform: translate(-50%, -20px);
  }
}
@keyframes combat-flash {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}
</style>
