# 🍿 MovieVerse — Advanced Telegram Movie Bot

A polished Telegram movie-discovery bot powered by **aiogram 3** and **TMDB**.

## Features

- 🔎 Movie search with posters, ratings and synopsis
- 🔥 Trending movies
- ⭐ Popular movies with pagination
- ❤️ Personal favorites/watchlist
- ▶️ Trailer shortcuts
- ⚡ Small in-memory TMDB cache to reduce repeated API calls
- 🛡️ Friendly error handling and structured logging
- 💾 SQLite persistence with WAL mode
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

Create a Telegram bot with BotFather and get a TMDB API key. Then set:

```text
BOT_TOKEN=...
TMDB_API_KEY=...
DATABASE_PATH=movies.db
CACHE_TTL=300
LOG_LEVEL=INFO
```

Run:

```bash
python bot.py
```

## Commands

`/start` — main menu  
`/search <title>` — search for a movie  
`/trending` — trending titles  
`/popular` — popular titles  
`/favorites` — saved movies  
`/help` — help menu

## Project files

- `bot.py` — Telegram handlers, TMDB client, keyboards and UI
- `database.py` — SQLite user/favorites persistence
- `requirements.txt` — Python dependencies
- `.env.example` — environment variable template
