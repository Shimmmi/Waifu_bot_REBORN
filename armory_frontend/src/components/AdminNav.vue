<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <nav class="tabs" style="margin: 1rem 0">
    <RouterLink to="/admin/players" class="tab">Игроки</RouterLink>
    <RouterLink to="/admin/group-chats" class="tab">Групповые чаты</RouterLink>
    <RouterLink to="/admin/tavern-bgm" class="tab">Tavern BGM</RouterLink>
    <RouterLink to="/admin/llm" class="tab">LLM</RouterLink>
    <RouterLink to="/admin/actions" class="tab">Журнал действий</RouterLink>
  </nav>
</template>
