import asyncio
import html
import logging
import os
import time
from typing import Any

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_PATH = os.getenv("DATABASE_PATH", "movies.db")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
PAGE_SIZE = 6

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("advanced-movie-bot")

dp = Dispatcher()
db = Database(DATABASE_PATH)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def tmdb(path: str, **params) -> dict[str, Any]:
    if not TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY is not configured")
    key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    params["api_key"] = TMDB_API_KEY
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{TMDB_BASE}{path}", params=params) as response:
            response.raise_for_status()
            data = await response.json()
    _cache[key] = (time.time(), data)
    return data


def home_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔎 Search Movies", callback_data="menu:search"))
    b.row(
        InlineKeyboardButton(text="🔥 Trending", callback_data="list:trending:1"),
        InlineKeyboardButton(text="⭐ Popular", callback_data="list:popular:1"),
    )
    b.row(
        InlineKeyboardButton(text="❤️ Favorites", callback_data="favorites:1"),
        InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help"),
    )
    return b.as_markup()


def movie_keyboard(movie_id: int, user_id: int, saved: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💔 Remove" if saved else "❤️ Save", callback_data=f"toggle:{movie_id}"))
    b.row(InlineKeyboardButton(text="🎬 Watch Trailer", url=f"https://www.youtube.com/results?search_query=movie+{movie_id}+official+trailer"))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def page_keyboard(kind: str, page: int, has_next: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"list:{kind}:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"list:{kind}:{page+1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def rating(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "N/A"


def movie_text(movie: dict[str, Any]) -> str:
    title = html.escape(movie.get("title") or movie.get("name") or "Unknown")
    date = (movie.get("release_date") or movie.get("first_air_date") or "")[:4] or "N/A"
    overview = html.escape(movie.get("overview") or "No synopsis available.")
    return f"🎬 <b>{title}</b> <i>({date})</i>\n\n⭐ <b>{rating(movie.get('vote_average'))}</b>/10\n\n{overview[:700]}"


async def send_movie(message: Message, movie: dict[str, Any], user_id: int):
    movie_id = int(movie["id"])
    saved = db.is_favorite(user_id, movie_id)
    caption = movie_text(movie)
    poster = movie.get("poster_path")
    keyboard = movie_keyboard(movie_id, user_id, saved)
    if poster:
        await message.answer_photo(f"{TMDB_IMAGE}{poster}", caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(caption, reply_markup=keyboard, parse_mode="HTML")


async def list_movies(message: Message, kind: str, page: int, user_id: int):
    endpoint = "/trending/movie/week" if kind == "trending" else "/movie/popular"
    params = {"language": "en-US"} if kind == "trending" else {"language": "en-US", "region": "IN"}
    if kind == "popular":
        params["page"] = page
    elif page > 1:
        # TMDB trending is one rolling endpoint; emulate simple paging locally.
        params["page"] = page
    data = await tmdb(endpoint, **params)
    movies = data.get("results", [])
    start = 0
    selected = movies[start:start + PAGE_SIZE]
    if not selected:
        await message.answer("😕 Nothing found on this page.", reply_markup=page_keyboard(kind, max(1, page - 1), False))
        return
    label = "🔥 Trending This Week" if kind == "trending" else "⭐ Popular Movies"
    await message.answer(f"<b>{label}</b>  ·  Page {page}", parse_mode="HTML")
    for movie in selected:
        try:
            await send_movie(message, movie, user_id)
        except TelegramBadRequest:
            log.exception("Failed to send movie %s", movie.get("id"))
    await message.answer("Choose a page:", reply_markup=page_keyboard(kind, page, bool(data.get("total_pages", 1) > page)))


@dp.message(CommandStart())
async def start(message: Message):
    db.upsert_user(message.from_user.id, message.from_user.username)
    name = html.escape(message.from_user.first_name or "there")
    await message.answer(
        f"🍿 <b>MovieVerse</b>\n\nHey {name}! 👋\nYour clean movie discovery hub for ratings, posters, trends and favorites.\n\n<b>Start exploring below.</b>",
        reply_markup=home_keyboard(),
        parse_mode="HTML",
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>📚 MovieVerse Help</b>\n\n/search &lt;title&gt; — find a movie\n/trending — trending titles\n/popular — popular titles\n/favorites — your saved movies\n/start — open the main menu\n\n<i>MovieVerse is for legal movie discovery and metadata only.</i>",
        parse_mode="HTML",
        reply_markup=home_keyboard(),
    )


@dp.message(Command("search"))
async def search_cmd(message: Message):
    query = message.text.partition(" ")[2].strip()
    if not query:
        await message.answer("🔎 Try: <code>/search Interstellar</code>", parse_mode="HTML")
        return
    status = await message.answer("🔎 Searching TMDB…")
    try:
        data = await tmdb("/search/movie", query=query, include_adult=False, language="en-US", page=1)
    except Exception:
        log.exception("TMDB search failed")
        await status.edit_text("⚠️ Search is temporarily unavailable. Please try again.")
        return
    results = data.get("results", [])[:PAGE_SIZE]
    if not results:
        await status.edit_text(f"😕 No movies found for <b>{html.escape(query)}</b>.", parse_mode="HTML")
        return
    await status.edit_text(f"🎯 <b>Results for:</b> {html.escape(query)}", parse_mode="HTML")
    for movie in results:
        await send_movie(message, movie, message.from_user.id)


@dp.message(Command("trending"))
async def trending_cmd(message: Message):
    try:
        await list_movies(message, "trending", 1, message.from_user.id)
    except Exception:
        log.exception("Trending failed")
        await message.answer("⚠️ Could not load trending movies right now.")


@dp.message(Command("popular"))
async def popular_cmd(message: Message):
    try:
        await list_movies(message, "popular", 1, message.from_user.id)
    except Exception:
        log.exception("Popular failed")
        await message.answer("⚠️ Could not load popular movies right now.")


async def show_favorites(message: Message, page: int):
    ids = db.get_favorites(message.from_user.id, limit=100)
    if not ids:
        await message.answer("❤️ <b>Your favorites are empty.</b>\n\nSave movies to build your personal watchlist.", reply_markup=home_keyboard(), parse_mode="HTML")
        return
    start = (page - 1) * PAGE_SIZE
    selected = ids[start:start + PAGE_SIZE]
    if not selected:
        await message.answer("No more favorites.", reply_markup=page_keyboard("favorites", max(1, page - 1), False))
        return
    await message.answer(f"❤️ <b>Your Favorites</b>  ·  Page {page}", parse_mode="HTML")
    for movie_id in selected:
        try:
            movie = await tmdb(f"/movie/{movie_id}", language="en-US")
            await send_movie(message, movie, message.from_user.id)
        except Exception:
            log.exception("Could not load favorite %s", movie_id)
    await message.answer("Choose a page:", reply_markup=page_keyboard("favorites", page, len(ids) > start + PAGE_SIZE))


@dp.message(Command("favorites"))
async def favorites_cmd(message: Message):
    await show_favorites(message, 1)


@dp.callback_query(F.data == "home")
async def home_cb(call: CallbackQuery):
    await call.message.edit_text("🍿 <b>MovieVerse</b>\n\nChoose what you want to explore:", reply_markup=home_keyboard(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "menu:help")
async def help_cb(call: CallbackQuery):
    await call.message.edit_text("<b>📚 Help</b>\n\nUse /search, /trending, /popular and /favorites.\n\nMovie discovery only — no unauthorized copies or streams.", reply_markup=home_keyboard(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "menu:search")
async def search_cb(call: CallbackQuery):
    await call.message.answer("🔎 Send <code>/search movie name</code> to find a title.", parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data.startswith("list:"))
async def list_cb(call: CallbackQuery):
    _, kind, page_raw = call.data.split(":")
    page = max(1, int(page_raw))
    await call.answer("Loading…")
    try:
        await list_movies(call.message, kind, page, call.from_user.id)
    except Exception:
        log.exception("List callback failed")
        await call.message.answer("⚠️ Could not load that page right now.")


@dp.callback_query(F.data.startswith("favorites:"))
async def favorites_cb(call: CallbackQuery):
    page = max(1, int(call.data.split(":", 1)[1]))
    await call.answer("Loading favorites…")
    await show_favorites(call.message, page)


@dp.callback_query(F.data.startswith("toggle:"))
async def toggle_cb(call: CallbackQuery):
    movie_id = int(call.data.split(":", 1)[1])
    if db.is_favorite(call.from_user.id, movie_id):
        db.remove_favorite(call.from_user.id, movie_id)
        await call.answer("💔 Removed from favorites")
    else:
        db.upsert_user(call.from_user.id, call.from_user.username)
        db.add_favorite(call.from_user.id, movie_id)
        await call.answer("❤️ Saved to favorites")
    try:
        current = call.message.reply_markup
        if current and call.message.caption:
            new_markup = movie_keyboard(movie_id, call.from_user.id, db.is_favorite(call.from_user.id, movie_id))
            await call.message.edit_reply_markup(reply_markup=new_markup)
        elif current:
            new_markup = movie_keyboard(movie_id, call.from_user.id, db.is_favorite(call.from_user.id, movie_id))
            await call.message.edit_reply_markup(reply_markup=new_markup)
    except TelegramBadRequest:
        pass


async def main():
    if not BOT_TOKEN or not TMDB_API_KEY:
        raise RuntimeError("Set BOT_TOKEN and TMDB_API_KEY environment variables")
    db.init()
    bot = Bot(BOT_TOKEN)
    log.info("MovieVerse bot starting")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
