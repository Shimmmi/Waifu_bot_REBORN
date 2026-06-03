import { createRouter, createWebHistory } from 'vue-router'
import Home from './pages/Home.vue'
import Player from './pages/Player.vue'
import Login from './pages/Login.vue'
import AdminDashboard from './pages/admin/Dashboard.vue'
import AdminPlayers from './pages/admin/Players.vue'
import AdminPlayerDetails from './pages/admin/PlayerDetails.vue'
import AdminActions from './pages/admin/Actions.vue'
import AdminGroupChats from './pages/admin/GroupChats.vue'

const router = createRouter({
  history: createWebHistory('/armory/'),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/login', name: 'login', component: Login },
    { path: '/p/:id', name: 'player', component: Player, props: true },
    { path: '/admin', name: 'admin', component: AdminDashboard },
    { path: '/admin/players', name: 'admin-players', component: AdminPlayers },
    { path: '/admin/players/:id', name: 'admin-player', component: AdminPlayerDetails, props: true },
    { path: '/admin/group-chats', name: 'admin-group-chats', component: AdminGroupChats },
    { path: '/admin/actions', name: 'admin-actions', component: AdminActions },
  ],
})

export default router
