import asyncio
import logging
import os
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("advanced-movie-bot")

dp = Dispatcher()
db = Database(os.getenv("DATABASE_PATH", "movies.db"))


async def tmdb(path: str, **params):
    if not TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY is not configured")
    params["api_key"] = TMDB_API_KEY
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{TMDB_BASE}{path}", params=params, timeout=15) as r:
            r.raise_for_status()
            return await r.json()


def home_keyboard():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔎 Search", callback_data="menu:search"))
    b.row(InlineKeyboardButton(text="🔥 Trending", callback_data="menu:trending"), InlineKeyboardButton(text="⭐ Popular", callback_data="menu:popular"))
    b.row(InlineKeyboardButton(text="❤️ Favorites", callback_data="menu:favorites"), InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help"))
    return b.as_markup()


def movie_keyboard(movie_id: int):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❤️ Save", callback_data=f"save:{movie_id}"))
    b.row(InlineKeyboardButton(text="▶️ Trailer", url=f"https://www.youtube.com/results?search_query=movie+{movie_id}+official+trailer"))
    b.row(InlineKeyboardButton(text="🔙 Home", callback_data="home"))
    return b.as_markup()


def movie_text(m: dict) -> str:
    title = m.get("title") or m.get("name") or "Unknown"
    date = (m.get("release_date") or m.get("first_air_date") or "")[:4] or "N/A"
    rating = m.get("vote_average")
    overview = m.get("overview") or "No synopsis available."
    return f"🎬 <b>{title}</b> ({date})\n\n⭐ Rating: <b>{rating:.1f}</b>/10\n\n{overview[:900]}"


async def send_movie(message: Message, movie: dict):
    text = movie_text(movie)
    poster = movie.get("poster_path")
    if poster:
        await message.answer_photo(f"{TMDB_IMAGE}{poster}", caption=text, reply_markup=movie_keyboard(movie["id"]), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=movie_keyboard(movie["id"]), parse_mode="HTML")


@dp.message(CommandStart())
async def start(message: Message):
    db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "🍿 <b>Advanced Movie Bot</b>\n\nSearch movies, discover trending titles, view ratings and save favorites.\n\nUse <code>/search movie name</code> to begin.",
        reply_markup=home_keyboard(), parse_mode="HTML"
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>Commands</b>\n/search &lt;title&gt; — search movies\n/trending — today's trending movies\n/popular — popular movies\n/favorites — your saved movies\n\nThis bot is for movie discovery and metadata. It does not provide unauthorized movie copies or streams.",
        parse_mode="HTML"
    )


@dp.message(Command("search"))
async def search_cmd(message: Message):
    query = message.text.partition(" ")[2].strip()
    if not query:
        await message.answer("Try: <code>/search Interstellar</code>", parse_mode="HTML")
        return
    data = await tmdb("/search/movie", query=query, include_adult=False, language="en-US", page=1)
    results = data.get("results", [])[:8]
    if not results:
        await message.answer("😕 No matching movies found.")
        return
    for movie in results:
        await send_movie(message, movie)


@dp.message(Command("trending"))
async def trending_cmd(message: Message):
    data = await tmdb("/trending/movie/week", language="en-US")
    for movie in data.get("results", [])[:8]:
        await send_movie(message, movie)


@dp.message(Command("popular"))
async def popular_cmd(message: Message):
    data = await tmdb("/movie/popular", language="en-US", page=1, region="IN")
    for movie in data.get("results", [])[:8]:
        await send_movie(message, movie)


@dp.message(Command("favorites"))
async def favorites_cmd(message: Message):
    ids = db.get_favorites(message.from_user.id)
    if not ids:
        await message.answer("❤️ Your favorites list is empty.")
        return
    for movie_id in ids[:20]:
        try:
            movie = await tmdb(f"/movie/{movie_id}", language="en-US")
            await send_movie(message, movie)
        except Exception:
            log.exception("Could not load movie %s", movie_id)


@dp.callback_query(F.data == "home")
async def home_cb(call: CallbackQuery):
    await call.message.edit_text("🍿 <b>Movie Hub</b>\n\nChoose an option:", reply_markup=home_keyboard(), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "menu:help")
async def help_cb(call: CallbackQuery):
    await call.message.edit_text("Use /search, /trending, /popular or /favorites.\n\nFor legal movie discovery only.", reply_markup=home_keyboard())
    await call.answer()


@dp.callback_query(F.data == "menu:search")
async def search_cb(call: CallbackQuery):
    await call.message.answer("🔎 Send <code>/search movie name</code>", parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "menu:trending")
async def trending_cb(call: CallbackQuery):
    await call.message.answer("🔥 Loading trending movies...")
    data = await tmdb("/trending/movie/week", language="en-US")
    for movie in data.get("results", [])[:8]:
        await send_movie(call.message, movie)
    await call.answer()


@dp.callback_query(F.data == "menu:popular")
async def popular_cb(call: CallbackQuery):
    await call.message.answer("⭐ Loading popular movies...")
    data = await tmdb("/movie/popular", language="en-US", page=1, region="IN")
    for movie in data.get("results", [])[:8]:
        await send_movie(call.message, movie)
    await call.answer()


@dp.callback_query(F.data == "menu:favorites")
async def favorites_cb(call: CallbackQuery):
    await favorites_cmd(call.message)
    await call.answer()


@dp.callback_query(F.data.startswith("save:"))
async def save_cb(call: CallbackQuery):
    movie_id = int(call.data.split(":", 1)[1])
    db.add_favorite(call.from_user.id, movie_id)
    await call.answer("❤️ Added to favorites")


async def main():
    if not BOT_TOKEN or not TMDB_API_KEY:
        raise RuntimeError("Set BOT_TOKEN and TMDB_API_KEY environment variables")
    db.init()
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
