<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
onMounted(() => auth.fetchMe())
</script>

<template>
  <div>
    <header class="header-nav">
      <RouterLink to="/" class="brand">Waifu_HUB</RouterLink>
      <nav>
        <RouterLink to="/" class="nav-link">Главная</RouterLink>
        <RouterLink v-if="auth.user" :to="`/p/${auth.user.telegram_id}`" class="nav-link">Мой профиль</RouterLink>
        <RouterLink v-if="auth.user?.is_admin" to="/admin" class="nav-link">Админ</RouterLink>
        <RouterLink v-if="!auth.user" to="/login" class="nav-link">Войти</RouterLink>
        <button v-else type="button" class="btn btn-sm btn-nav" @click="auth.logout()">Выйти</button>
      </nav>
    </header>
    <main class="container">
      <RouterView />
    </main>
    <div class="item-art-gen-busy-overlay" aria-live="polite" aria-busy="true">
      <div class="item-art-gen-busy-panel">
        <div class="item-art-gen-busy-spinner" aria-hidden="true" />
        <p>Генерация иконки…</p>
        <p class="item-art-gen-busy-hint">Генерация может занять до 2 минут</p>
      </div>
    </div>
  </div>
</template>
