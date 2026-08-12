import sqlite3
from contextlib import contextmanager


class Database:
    def __init__(self, path: str = "movies.db"):
        self.path = path

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self):
        with self.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER NOT NULL, movie_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, movie_id))")

    def upsert_user(self, user_id: int, username: str | None):
        with self.connection() as conn:
            conn.execute("INSERT INTO users(user_id, username) VALUES(?, ?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username", (user_id, username))

    def add_favorite(self, user_id: int, movie_id: int):
        with self.connection() as conn:
            conn.execute("INSERT OR IGNORE INTO favorites(user_id, movie_id) VALUES(?, ?)", (user_id, movie_id))

    def get_favorites(self, user_id: int):
        with self.connection() as conn:
            return [row[0] for row in conn.execute("SELECT movie_id FROM favorites WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()]
