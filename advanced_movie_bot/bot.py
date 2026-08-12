import asyncio
import html
import logging
import os
import time
from typing import Any

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
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
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "").strip()
FORCE_JOIN_URL = os.getenv("FORCE_JOIN_URL", "").strip()

GENRES = {
    "28": "Action", "12": "Adventure", "16": "Animation", "35": "Comedy", "80": "Crime",
    "99": "Documentary", "18": "Drama", "10751": "Family", "14": "Fantasy", "36": "History",
    "27": "Horror", "10402": "Music", "9648": "Mystery", "10749": "Romance", "878": "Sci-Fi",
    "53": "Thriller", "10752": "War", "37": "Western",
}
LANGUAGES = {"en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "ko": "Korean", "ja": "Japanese"}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("movieverse")

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


async def require_join(message: Message) -> bool:
    if not FORCE_JOIN_CHANNEL:
        return True
    try:
        member = await message.bot.get_chat_member(FORCE_JOIN_CHANNEL, message.from_user.id)
        allowed = member.status not in {"left", "kicked"}
    except Exception:
        log.exception("Force-join check failed")
        return True
    if allowed:
        return True
    b = InlineKeyboardBuilder()
    if FORCE_JOIN_URL:
        b.row(InlineKeyboardButton(text="📢 Join Channel", url=FORCE_JOIN_URL))
    b.row(InlineKeyboardButton(text="✅ I've Joined", callback_data="checkjoin"))
    await message.answer("🔒 <b>Join our channel first</b>\n\nJoin the required channel, then tap <b>I've Joined</b>.", reply_markup=b.as_markup(), parse_mode="HTML")
    return False


def home_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔎 Search", callback_data="menu:search"), InlineKeyboardButton(text="🎭 Genres", callback_data="menu:genres"))
    b.row(InlineKeyboardButton(text="🔥 Trending", callback_data="list:trending:1"), InlineKeyboardButton(text="⭐ Popular", callback_data="list:popular:1"))
    b.row(InlineKeyboardButton(text="🌎 Languages", callback_data="menu:languages"), InlineKeyboardButton(text="❤️ Favorites", callback_data="favorites:1"))
    b.row(InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help"))
    return b.as_markup()


def genres_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    rows = list(GENRES.items())
    for i in range(0, len(rows), 2):
        pair = rows[i:i + 2]
        b.row(*(InlineKeyboardButton(text=name, callback_data=f"genre:{gid}:1") for gid, name in pair))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def languages_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*(InlineKeyboardButton(text=name, callback_data=f"lang:{code}:1") for code, name in list(LANGUAGES.items())[:3]))
    b.row(*(InlineKeyboardButton(text=name, callback_data=f"lang:{code}:1") for code, name in list(LANGUAGES.items())[3:]))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def movie_keyboard(movie_id: int, saved: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💔 Remove" if saved else "❤️ Save", callback_data=f"toggle:{movie_id}"))
    b.row(InlineKeyboardButton(text="📖 Details", callback_data=f"detail:{movie_id}"), InlineKeyboardButton(text="🎬 Trailer", url=f"https://www.youtube.com/results?search_query=movie+{movie_id}+official+trailer"))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


def page_keyboard(kind: str, page: int, has_next: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder(); nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"{kind}:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"{kind}:{page+1}"))
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
    keyboard = movie_keyboard(movie_id, saved)
    if poster:
        await message.answer_photo(f"{TMDB_IMAGE}{poster}", caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(caption, reply_markup=keyboard, parse_mode="HTML")


async def send_detail(message: Message, movie_id: int):
    movie = await tmdb(f"/movie/{movie_id}", language="en-US", append_to_response="credits,videos,similar")
    title = html.escape(movie.get("title", "Unknown"))
    genres = ", ".join(g.get("name", "") for g in movie.get("genres", [])) or "N/A"
    runtime = movie.get("runtime") or "N/A"
    release = movie.get("release_date") or "N/A"
    cast = ", ".join(html.escape(c.get("name", "")) for c in movie.get("credits", {}).get("cast", [])[:5]) or "N/A"
    similar = movie.get("similar", {}).get("results", [])[:4]
    text = (f"🎬 <b>{title}</b>\n\n⭐ Rating: <b>{rating(movie.get('vote_average'))}</b>/10\n"
            f"📅 Release: <b>{release}</b>\n⏱ Runtime: <b>{runtime} min</b>\n🎭 Genres: <b>{html.escape(genres)}</b>\n\n"
            f"👥 Cast: {cast}\n\n{html.escape(movie.get('overview') or 'No synopsis available.')[:1200]}")
    await message.answer(text, reply_markup=movie_keyboard(movie_id, db.is_favorite(message.from_user.id, movie_id)), parse_mode="HTML")
    if similar:
        await message.answer("✨ <b>Similar movies</b>", parse_mode="HTML")
        for item in similar:
            await send_movie(message, item, message.from_user.id)


async def list_movies(message: Message, endpoint: str, page: int, user_id: int, params: dict[str, Any], label: str, callback_prefix: str):
    params = dict(params); params["page"] = page
    data = await tmdb(endpoint, **params)
    movies = data.get("results", [])
    if not movies:
        await message.answer("😕 No movies found on this page.")
        return
    await message.answer(f"<b>{label}</b>  ·  Page {page}", parse_mode="HTML")
    for movie in movies[:PAGE_SIZE]:
        try:
            await send_movie(message, movie, user_id)
        except TelegramBadRequest:
            log.exception("Failed to send movie %s", movie.get("id"))
    await message.answer("Choose a page:", reply_markup=page_keyboard(callback_prefix, page, data.get("total_pages", 1) > page))


async def show_favorites(message: Message, page: int):
    ids = db.get_favorites(message.from_user.id, limit=100)
    start = (page - 1) * PAGE_SIZE
    selected = ids[start:start + PAGE_SIZE]
    if not selected:
        text = "❤️ <b>Your favorites are empty.</b>" if not ids else "No more favorites."
        await message.answer(text, reply_markup=home_keyboard(), parse_mode="HTML")
        return
    await message.answer(f"❤️ <b>Your Favorites</b> · Page {page}", parse_mode="HTML")
    for movie_id in selected:
        try:
            await send_movie(message, await tmdb(f"/movie/{movie_id}", language="en-US"), message.from_user.id)
        except Exception:
            log.exception("Favorite load failed: %s", movie_id)
    await message.answer("Choose a page:", reply_markup=page_keyboard("favorites", page, len(ids) > start + PAGE_SIZE))


@dp.message(CommandStart())
async def start(message: Message):
    if not await require_join(message): return
    db.upsert_user(message.from_user.id, message.from_user.username)
    name = html.escape(message.from_user.first_name or "there")
    await message.answer(f"🍿 <b>MovieVerse</b>\n\nHey {name}! 👋\nDiscover movies, ratings, genres, cast and more.\n\n<b>Choose an option below.</b>", reply_markup=home_keyboard(), parse_mode="HTML")


@dp.message(Command("search"))
async def search_cmd(message: Message):
    if not await require_join(message): return
    query = message.text.partition(" ")[2].strip()
    if not query:
        await message.answer("🔎 Try: <code>/search Interstellar</code>", parse_mode="HTML"); return
    status = await message.answer("🔎 Searching…")
    try:
        data = await tmdb("/search/movie", query=query, include_adult=False, language="en-US", page=1)
        results = data.get("results", [])[:PAGE_SIZE]
        if not results:
            await status.edit_text(f"😕 No movies found for <b>{html.escape(query)}</b>.", parse_mode="HTML"); return
        await status.edit_text(f"🎯 <b>Results for:</b> {html.escape(query)}", parse_mode="HTML")
        for movie in results: await send_movie(message, movie, message.from_user.id)
    except Exception:
        log.exception("Search failed"); await status.edit_text("⚠️ Search is temporarily unavailable.")


@dp.message(Command("trending"))
async def trending_cmd(message: Message):
    if await require_join(message):
        await list_movies(message, "/trending/movie/week", 1, message.from_user.id, {"language": "en-US"}, "🔥 Trending This Week", "trending")


@dp.message(Command("popular"))
async def popular_cmd(message: Message):
    if await require_join(message):
        await list_movies(message, "/movie/popular", 1, message.from_user.id, {"language": "en-US", "region": "IN"}, "⭐ Popular Movies", "popular")


@dp.message(Command("favorites"))
async def favorites_cmd(message: Message):
    if await require_join(message): await show_favorites(message, 1)


@dp.message(Command("genres"))
async def genres_cmd(message: Message):
    if await require_join(message): await message.answer("🎭 <b>Browse by Genre</b>", reply_markup=genres_keyboard(), parse_mode="HTML")


@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    users = db.count_users(); favs = db.count_favorites()
    await message.answer(f"🛠 <b>Admin Panel</b>\n\n👤 Users: <b>{users}</b>\n❤️ Favorites: <b>{favs}</b>\n📦 Cache entries: <b>{len(_cache)}</b>", reply_markup=admin_keyboard(), parse_mode="HTML")


def admin_keyboard():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Refresh Stats", callback_data="admin:stats"))
    b.row(InlineKeyboardButton(text="🧹 Clear Cache", callback_data="admin:cache"))
    b.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return b.as_markup()


@dp.callback_query(F.data == "checkjoin")
async def checkjoin(call: CallbackQuery):
    fake = call.message
    if await require_join(fake):
        await call.answer("✅ Verified!"); await call.message.edit_text("🍿 <b>Welcome to MovieVerse</b>", reply_markup=home_keyboard(), parse_mode="HTML")
    else:
        await call.answer("❌ Please join the channel first", show_alert=True)


@dp.callback_query(F.data == "home")
async def home_cb(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text("🍿 <b>MovieVerse</b>\n\nChoose what you want to explore:", reply_markup=home_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "menu:search")
async def search_cb(call: CallbackQuery):
    await call.answer(); await call.message.answer("🔎 Send <code>/search movie name</code>", parse_mode="HTML")


@dp.callback_query(F.data == "menu:help")
async def help_cb(call: CallbackQuery):
    await call.answer(); await call.message.edit_text("<b>📚 MovieVerse</b>\n\n/search, /trending, /popular, /favorites, /genres\n\nUse buttons for discovery and detailed movie pages.", reply_markup=home_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "menu:genres")
async def genre_menu_cb(call: CallbackQuery):
    await call.answer(); await call.message.edit_text("🎭 <b>Browse by Genre</b>", reply_markup=genres_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "menu:languages")
async def language_menu_cb(call: CallbackQuery):
    await call.answer(); await call.message.edit_text("🌎 <b>Browse by Language</b>", reply_markup=languages_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "admin:stats")
async def admin_stats_cb(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return await call.answer("Not authorized", show_alert=True)
    await call.answer(); await call.message.edit_text(f"🛠 <b>Admin Stats</b>\n\n👤 Users: <b>{db.count_users()}</b>\n❤️ Favorites: <b>{db.count_favorites()}</b>\n📦 Cache: <b>{len(_cache)}</b>", reply_markup=admin_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "admin:cache")
async def admin_cache_cb(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return await call.answer("Not authorized", show_alert=True)
    _cache.clear(); await call.answer("🧹 Cache cleared"); await call.message.edit_reply_markup(reply_markup=admin_keyboard())


@dp.callback_query(F.data.startswith("toggle:"))
async def toggle_cb(call: CallbackQuery):
    movie_id = int(call.data.split(":", 1)[1])
    if db.is_favorite(call.from_user.id, movie_id): db.remove_favorite(call.from_user.id, movie_id); msg = "💔 Removed"
    else: db.upsert_user(call.from_user.id, call.from_user.username); db.add_favorite(call.from_user.id, movie_id); msg = "❤️ Saved"
    await call.answer(msg)
    try: await call.message.edit_reply_markup(reply_markup=movie_keyboard(movie_id, db.is_favorite(call.from_user.id, movie_id)))
    except TelegramBadRequest: pass


@dp.callback_query(F.data.startswith("detail:"))
async def detail_cb(call: CallbackQuery):
    await call.answer("Loading details…")
    try: await send_detail(call.message, int(call.data.split(":", 1)[1]))
    except Exception: log.exception("Details failed"); await call.message.answer("⚠️ Details unavailable right now.")


@dp.callback_query(F.data.startswith("trending:"))
async def trending_page_cb(call: CallbackQuery):
    await call.answer("Loading…"); await list_movies(call.message, "/trending/movie/week", int(call.data.split(":")[1]), call.from_user.id, {"language": "en-US"}, "🔥 Trending This Week", "trending")


@dp.callback_query(F.data.startswith("popular:"))
async def popular_page_cb(call: CallbackQuery):
    await call.answer("Loading…"); await list_movies(call.message, "/movie/popular", int(call.data.split(":")[1]), call.from_user.id, {"language": "en-US", "region": "IN"}, "⭐ Popular Movies", "popular")


@dp.callback_query(F.data.startswith("favorites:"))
async def favorites_page_cb(call: CallbackQuery):
    await call.answer("Loading…"); await show_favorites(call.message, int(call.data.split(":")[1]))


@dp.callback_query(F.data.startswith("genre:"))
async def genre_cb(call: CallbackQuery):
    _, gid, page = call.data.split(":")
    await call.answer("Loading genre…")
    await list_movies(call.message, "/discover/movie", int(page), call.from_user.id, {"language": "en-US", "sort_by": "popularity.desc", "with_genres": gid}, f"🎭 {GENRES.get(gid, 'Genre')}", f"genre:{gid}")


@dp.callback_query(F.data.startswith("lang:"))
async def lang_cb(call: CallbackQuery):
    _, code, page = call.data.split(":")
    await call.answer("Loading language…")
    await list_movies(call.message, "/discover/movie", int(page), call.from_user.id, {"language": "en-US", "sort_by": "popularity.desc", "with_original_language": code}, f"🌎 {LANGUAGES.get(code, code)} Movies", f"lang:{code}")


async def main():
    if not BOT_TOKEN or not TMDB_API_KEY: raise RuntimeError("Set BOT_TOKEN and TMDB_API_KEY environment variables")
    db.init(); bot = Bot(BOT_TOKEN); log.info("MovieVerse starting"); await dp.start_polling(bot)


if __name__ == "__main__": asyncio.run(main())
