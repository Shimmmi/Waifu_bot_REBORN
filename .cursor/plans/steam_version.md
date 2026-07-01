## План миграции на Steam с сохранением Telegram-бота

---

## Фаза 0: Аудит кодовой базы (1-2 дня)

Прежде чем писать новый код — нужно понять что есть. В Cursor:

```
Ctrl+Shift+P → "Explain codebase"
```

Что нужно выяснить и зафиксировать:

**Создай файл `ARCHITECTURE.md` в корне проекта:**
```markdown
## Текущая структура

### Точки входа
- main.py / bot.py — где запускается бот

### Игровая логика (нужно сохранить)
- battle.py — механики боя
- dungeon.py — подземелья  
- loot.py — лут и награды
- expedition.py — экспедиции

### Telegram-зависимый код (нужно изолировать)
- handlers/ — все хендлеры aiogram
- keyboards/ — inline/reply клавиатуры

### Внешние зависимости
- OpenRouter — какие вызовы, где
- БД — PostgreSQL / SQLite, ORM или сырые запросы

### Mini App
- Где лежат HTML/JS файлы
- Как раздаются (nginx / python static)
```

---

## Фаза 1: Изоляция игровой логики (3-5 дней)

Это самый важный этап. Цель — чтобы игровая логика **ничего не знала о Telegram**.

### 1.1 Структура папок после рефакторинга

```
waifu-game/
├── core/                    ← ИГРОВАЯ ЛОГИКА (чистый Python, без Telegram)
│   ├── __init__.py
│   ├── battle.py
│   ├── dungeon.py
│   ├── character.py
│   ├── loot.py
│   ├── expedition.py
│   ├── skills.py
│   └── openrouter.py        ← изолированный клиент OpenRouter
│
├── api/                     ← FastAPI (новый слой)
│   ├── __init__.py
│   ├── main.py
│   ├── routes/
│   │   ├── battle.py
│   │   ├── dungeon.py
│   │   └── expedition.py
│   └── websocket.py         ← для real-time обновлений HP и т.д.
│
├── telegram/                ← TELEGRAM БОТ (только транспорт)
│   ├── __init__.py
│   ├── bot.py
│   ├── handlers/
│   └── keyboards/
│
├── electron/                ← PC-приложение (новое)
│   ├── main.js
│   ├── preload.js
│   └── input_tracker.py     ← pynput хуки
│
├── frontend/                ← существующий HTML/JS Mini App
│   ├── profile.html
│   ├── dungeons.html
│   └── ...
│
├── db/
│   ├── models.py
│   └── migrations/
│
├── config.py                ← все настройки централизованно
├── requirements.txt
└── .env
```

### 1.2 Создание единого конфига

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # БД
    DATABASE_URL: str
    
    # OpenRouter
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str = "anthropic/claude-3-haiku"
    
    # Telegram (опционально — бот может не запускаться)
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_ENABLED: bool = True
    
    # API сервер
    API_HOST: str = "localhost"
    API_PORT: int = 8000
    
    # Игровые параметры (то что сейчас в БД-переменных)
    BASE_ELITE_CHANCE: float = 0.06
    EXPEDITION_TICK_MIN: int = 5
    EXPEDITION_TICK_MAX: int = 10
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### 1.3 Паттерн рефакторинга хендлеров

Покажи Cursor один хендлер и попроси разделить:

```python
# БЫЛО: логика внутри хендлера
@router.message(StateFilter(InDungeon))
async def handle_attack(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    dungeon = await db.get_active_dungeon(user_id)
    
    # Вся логика прямо здесь
    damage = random.randint(dungeon.dmg_min, dungeon.dmg_max)
    crit = random.random() < character.crit_chance
    if crit:
        damage *= 1.5
    dungeon.monster_hp -= damage
    await db.save_dungeon(dungeon)
    
    await message.answer(f"Удар! Урон: {damage}")

# СТАЛО: хендлер только транспорт
@router.message(StateFilter(InDungeon))
async def handle_attack(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Определяем тип атаки
    attack_type = detect_attack_type(message)  # text/sticker/photo/etc
    
    # Вызываем игровую логику
    result = await game_engine.process_attack(
        user_id=user_id,
        attack_type=attack_type
    )
    
    # Форматируем ответ для Telegram
    await message.answer(format_attack_result(result))
```

**Промпт для Cursor:**
```
Refactor this file: extract all game logic into core/ module,
leaving only Telegram message formatting in the handler.
The core function should return a dataclass/TypedDict result
with no Telegram dependencies.
```

---

## Фаза 2: FastAPI сервер (3-4 дня)

### 2.1 Основной файл API

```python
# api/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import battle, dungeon, expedition, character
from api.websocket import ws_router

app = FastAPI(title="Waifu Game API")

# Для Electron и браузера
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # в продакшне сузить
    allow_methods=["*"],
    allow_headers=["*"],
)

# Существующий Mini App фронтенд раздаём напрямую
app.mount("/app", StaticFiles(directory="frontend"), name="frontend")

# Маршруты
app.include_router(battle.router, prefix="/api/battle")
app.include_router(dungeon.router, prefix="/api/dungeon")
app.include_router(expedition.router, prefix="/api/expedition")
app.include_router(character.router, prefix="/api/character")
app.include_router(ws_router)
```

### 2.2 Ключевые эндпоинты

```python
# api/routes/battle.py
from fastapi import APIRouter
from core.battle import game_engine
from pydantic import BaseModel

router = APIRouter()

class AttackRequest(BaseModel):
    user_id: int
    attack_type: str  # "text", "click", "keypress", "sticker", "photo"
    
class AttackResult(BaseModel):
    damage: int
    is_crit: bool
    monster_hp_remaining: int
    monster_dead: bool
    loot: dict | None

@router.post("/attack", response_model=AttackResult)
async def process_attack(req: AttackRequest):
    return await game_engine.process_attack(
        user_id=req.user_id,
        attack_type=req.attack_type
    )

@router.get("/state/{user_id}")
async def get_battle_state(user_id: int):
    return await game_engine.get_state(user_id)
```

### 2.3 WebSocket для real-time UI

```python
# api/websocket.py
from fastapi import APIRouter, WebSocket
from typing import dict

router = APIRouter()
connections: dict[int, WebSocket] = {}

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    connections[user_id] = websocket
    try:
        while True:
            # Держим соединение живым
            await websocket.receive_text()
    except:
        del connections[user_id]

async def notify_user(user_id: int, event: dict):
    """Вызывается из game_engine при любом игровом событии"""
    if user_id in connections:
        await connections[user_id].send_json(event)
```

---

## Фаза 3: Параллельный запуск Telegram-бота (1-2 дня)

Это делается **сейчас**, до работы с Electron — чтобы бот продолжал работать.

### 3.1 Точка входа с выбором режима

```python
# run.py — единая точка запуска
import asyncio
import argparse
import uvicorn
from config import settings

async def run_all():
    """Запуск API + Telegram бота одновременно"""
    tasks = []
    
    # FastAPI всегда запускается
    config = uvicorn.Config(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    tasks.append(asyncio.create_task(server.serve()))
    
    # Telegram бот — опционально
    if settings.TELEGRAM_ENABLED and settings.TELEGRAM_TOKEN:
        from telegram.bot import start_bot
        tasks.append(asyncio.create_task(start_bot()))
        print("✅ Telegram bot started")
    else:
        print("⏭️ Telegram bot disabled")
    
    print(f"✅ API started at http://{settings.API_HOST}:{settings.API_PORT}")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()
    
    if args.no_telegram:
        settings.TELEGRAM_ENABLED = False
    
    asyncio.run(run_all())
```

### 3.2 .env для переключения режимов

```bash
# .env.telegram — боевой Telegram режим
TELEGRAM_ENABLED=true
TELEGRAM_TOKEN=your_token_here

# .env.pc — только PC режим
TELEGRAM_ENABLED=false
TELEGRAM_TOKEN=

# .env.dev — разработка (оба отключены, только API)
TELEGRAM_ENABLED=false
```

```bash
# Запуск вариантов:
python run.py                    # API + Telegram
python run.py --no-telegram      # только API (для PC-режима)
```

---

## Фаза 4: Electron-оболочка (4-5 дней)

### 4.1 Инициализация Electron проекта

```bash
# В папке electron/
npm init -y
npm install electron electron-builder
npm install node-fetch ws  # для общения с Python API
```

### 4.2 Главный процесс Electron

```javascript
// electron/main.js
const { app, BrowserWindow, Tray, Menu, ipcMain } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let mainWindow = null
let tray = null
let pythonProcess = null

// Запуск Python API как дочернего процесса
function startPythonBackend() {
    pythonProcess = spawn('python', [
        path.join(__dirname, '../run.py'),
        '--no-telegram'
    ])
    
    pythonProcess.stdout.on('data', (data) => {
        console.log(`Python: ${data}`)
    })
    
    pythonProcess.stderr.on('data', (data) => {
        console.error(`Python error: ${data}`)
    })
    
    // Ждём пока API поднимется
    return new Promise(resolve => setTimeout(resolve, 2000))
}

async function createWindow() {
    await startPythonBackend()
    
    mainWindow = new BrowserWindow({
        width: 400,
        height: 700,
        frame: false,           // без системной рамки
        transparent: true,      // для оверлея
        alwaysOnTop: true,      // поверх всех окон
        skipTaskbar: false,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        }
    })
    
    // Загружаем существующий Mini App
    mainWindow.loadURL('http://localhost:8000/app/dungeons.html')
}

// Трей-иконка
function createTray() {
    tray = new Tray(path.join(__dirname, 'assets/tray-icon.png'))
    
    const menu = Menu.buildFromTemplate([
        { label: 'Открыть игру', click: () => mainWindow.show() },
        { label: 'Профиль', click: () => mainWindow.loadURL('http://localhost:8000/app/profile.html') },
        { type: 'separator' },
        { label: 'Выйти', click: () => app.quit() }
    ])
    
    tray.setContextMenu(menu)
    tray.setToolTip('Waifu Game — активна')
}

app.whenReady().then(async () => {
    await createWindow()
    createTray()
    
    // Старт отслеживания ввода
    ipcMain.emit('start-input-tracking')
})

app.on('before-quit', () => {
    if (pythonProcess) pythonProcess.kill()
})
```

### 4.3 Preload — мост между Electron и фронтендом

```javascript
// electron/preload.js
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
    // Уведомить о нажатии (из input tracker)
    onInputEvent: (callback) => {
        ipcRenderer.on('input-event', (_, data) => callback(data))
    },
    
    // Управление окном
    minimizeToTray: () => ipcRenderer.send('minimize-to-tray'),
    
    // Текущий пользователь (из локального стора)
    getUserId: () => ipcRenderer.invoke('get-user-id')
})
```

### 4.4 Отслеживание ввода

```python
# electron/input_tracker.py
# Запускается как отдельный процесс, шлёт события в API
import asyncio
import httpx
from pynput import keyboard, mouse
from collections import deque
import time

class InputTracker:
    def __init__(self, user_id: int, api_url: str):
        self.user_id = user_id
        self.api_url = api_url
        # Дебаунс: не слать каждое нажатие, группировать
        self.pending_attacks = 0
        self.last_send = time.time()
        self.BATCH_INTERVAL = 0.5  # секунды
        
    async def send_attacks(self):
        """Отправка накопленных атак пачкой"""
        while True:
            await asyncio.sleep(self.BATCH_INTERVAL)
            if self.pending_attacks > 0:
                async with httpx.AsyncClient() as client:
                    await client.post(f"{self.api_url}/api/battle/attack-batch", json={
                        "user_id": self.user_id,
                        "attack_type": "keypress",
                        "count": self.pending_attacks
                    })
                self.pending_attacks = 0
    
    def on_key_press(self, key):
        # Игнорируем системные клавиши
        ignore = {keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.cmd}
        if key not in ignore:
            self.pending_attacks += 1
    
    def on_click(self, x, y, button, pressed):
        if pressed:
            attack_type = "skill" if button == mouse.Button.right else "click"
            # Клики отправляем сразу (редкое действие)
            asyncio.run(self._send_single(attack_type))
    
    async def _send_single(self, attack_type: str):
        async with httpx.AsyncClient() as client:
            await client.post(f"{self.api_url}/api/battle/attack", json={
                "user_id": self.user_id,
                "attack_type": attack_type
            })
    
    def start(self):
        asyncio.run(self._run())
    
    async def _run(self):
        kb = keyboard.Listener(on_press=self.on_key_press)
        ms = mouse.Listener(on_click=self.on_click)
        kb.start()
        ms.start()
        await self.send_attacks()
```

---

## Фаза 5: Адаптация фронтенда (2-3 дня)

Изменения **минимальные** — фронтенд уже написан.

### 5.1 Что менять в HTML/JS

```javascript
// Было: Telegram WebApp API
window.Telegram.WebApp.sendData(JSON.stringify(data))
const userId = window.Telegram.WebApp.initDataUnsafe.user.id

// Стало: универсальный адаптер
const Platform = {
    getUserId: async () => {
        if (window.electronAPI) {
            // PC режим
            return await window.electronAPI.getUserId()
        } else if (window.Telegram?.WebApp) {
            // Telegram режим  
            return window.Telegram.WebApp.initDataUnsafe.user.id
        } else {
            // Браузер/дев режим
            return localStorage.getItem('dev_user_id') || 1
        }
    },
    
    onAttack: (callback) => {
        if (window.electronAPI) {
            window.electronAPI.onInputEvent(callback)
        }
        // В Telegram — атаки приходят через WebSocket
    }
}

// WebSocket для real-time обновлений (работает везде)
const userId = await Platform.getUserId()
const ws = new WebSocket(`ws://localhost:8000/ws/${userId}`)
ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    updateUI(data)  // обновить HP, золото, лут
}
```

---

## Фаза 6: Steam-интеграция (2-3 дня)

### 6.1 Регистрация и настройка

```
1. Зарегистрировать аккаунт Steamworks: partner.steamgames.com
2. Оплатить Steam Direct: $100
3. Получить AppID
4. Добавить AppID в конфиг
```

### 6.2 Steamworks в Electron

```javascript
// electron/steam.js
const greenworks = require('greenworks')  // npm install greenworks

class SteamIntegration {
    constructor() {
        this.initialized = false
    }
    
    init() {
        try {
            if (greenworks.init()) {
                this.initialized = true
                console.log(`Steam: logged in as ${greenworks.getSteamId().getAccountId()}`)
            }
        } catch(e) {
            console.log('Steam not available, running without it')
        }
    }
    
    // Достижения
    unlockAchievement(name) {
        if (!this.initialized) return
        // 'KILL_1000_MONSTERS', 'FIRST_DUNGEON', etc.
        greenworks.activateAchievement(name, () => {})
    }
    
    // Таблица лидеров
    async updateLeaderboard(name, score) {
        if (!this.initialized) return
        return new Promise(resolve => {
            greenworks.findLeaderboard(name, (err, handle) => {
                greenworks.uploadLeaderboardScore(handle, score, () => resolve())
            })
        })
    }
    
    // Steam Cloud сохранения
    saveToCloud(filename, data) {
        if (!this.initialized) return
        greenworks.saveTextToFile(filename, JSON.stringify(data))
    }
}

module.exports = new SteamIntegration()
```

---

## Фаза 7: Сборка и дистрибуция (2-3 дня)

### 7.1 Конфиг electron-builder

```json
// package.json
{
  "scripts": {
    "start": "electron .",
    "build:win": "electron-builder --win",
    "build:mac": "electron-builder --mac",
    "build:linux": "electron-builder --linux"
  },
  "build": {
    "appId": "com.yourname.waifugame",
    "productName": "Waifu Game",
    "files": [
      "electron/**/*",
      "frontend/**/*"
    ],
    "extraResources": [
      {
        "from": "../",
        "to": "python",
        "filter": ["core/**", "api/**", "db/**", "*.py", "requirements.txt"]
      }
    ],
    "win": {
      "target": "nsis",
      "icon": "assets/icon.ico"
    },
    "nsis": {
      "oneClick": false,
      "allowToChangeInstallationDirectory": true
    }
  }
}
```

### 7.2 Упаковка Python-бэкенда

```bash
# PyInstaller собирает Python в .exe без установки Python у пользователя
pip install pyinstaller

pyinstaller --onefile \
  --hidden-import=uvicorn \
  --hidden-import=pynput \
  --add-data "core;core" \
  --add-data "api;api" \
  run.py

# Результат: dist/run.exe — включается в установщик Steam
```

---

## Общий таймлайн

```
Неделя 1: Фазы 0-1 (аудит + изоляция логики)
Неделя 2: Фаза 2-3 (FastAPI + параллельный Telegram)
           ← здесь бот уже работает на новой архитектуре
Неделя 3: Фаза 4 (Electron + pynput)
Неделя 4: Фазы 5-6 (фронтенд адаптация + Steam SDK)
Неделя 5: Фаза 7 + тесты + сборка
```

---

## Промпты для Cursor на каждую фазу

```
Фаза 1: "Extract all game logic from telegram/handlers/ into 
         core/ module. Each function should take plain Python 
         types, no aiogram dependencies."

Фаза 2: "Create FastAPI routes for core/ functions. 
         Add Pydantic request/response models. 
         Keep existing function signatures."

Фаза 4: "Create Electron main.js that spawns Python process,
         loads localhost:8000, and sets alwaysOnTop."

Фаза 4: "Create pynput listener that batches keypresses 
         and POSTs to FastAPI every 500ms."
```

Главный принцип всего переезда: **не переписывать, а изолировать**. Python-логика не меняется, Telegram-бот продолжает работать, Electron просто добавляет новый способ взаимодействия с тем же бэкендом.