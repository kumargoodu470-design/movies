# 🍿 MovieVerse — Advanced Telegram Movie Bot

A polished Telegram movie-discovery bot powered by **aiogram 3** and **TMDB**.

## Features

- 🔎 Movie search with posters, ratings and synopsis
- 🔥 Trending and ⭐ popular feeds with pagination
- 🎭 Browse by genre
- 🌎 Browse by selected language
- 📖 Detailed movie pages with release date, runtime, genres and top cast
- ✨ Similar movie recommendations
- ❤️ Personal favorites/watchlist
- 🎬 Trailer shortcuts
- 🔐 Optional force-subscribe gate
- 🛠 Admin stats and cache controls
- ⚡ In-memory TMDB cache to reduce repeated API calls
- 🛡️ Friendly error handling and structured logging
- 💾 SQLite persistence with WAL mode and indexes
- 🐳 Standalone Docker deployment
- 📱 Inline-button-first Telegram UI

> MovieVerse is designed for legal movie discovery and metadata. It does not provide unauthorized movie copies or streams.

## Setup

```bash
cd advanced_movie_bot
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure:

```text
BOT_TOKEN=...
TMDB_API_KEY=...
DATABASE_PATH=movies.db
CACHE_TTL=300
LOG_LEVEL=INFO
ADMIN_IDS=123456789
FORCE_JOIN_CHANNEL=@yourchannel
FORCE_JOIN_URL=https://t.me/yourchannel
```

Run:

```bash
python bot.py
```

## Docker

```bash
docker build -t movieverse-bot .
docker run --env-file .env movieverse-bot
```

## Commands

`/start` — main menu  
`/search <title>` — search for a movie  
`/trending` — trending titles  
`/popular` — popular titles  
`/favorites` — saved movies  
`/genres` — genre browser  
`/admin` — admin panel (admin IDs only)  
`/help` — help menu

## Project files

- `bot.py` — Telegram handlers, TMDB client, keyboards and UI
- `database.py` — SQLite user/favorites persistence and stats
- `requirements.txt` — Python dependencies
- `.env.example` — environment variable template
- `Dockerfile` — standalone deployment image
