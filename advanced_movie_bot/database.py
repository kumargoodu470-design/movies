import sqlite3
from contextlib import closing


class Database:
    def __init__(self, path: str):
        self.path = path

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self):
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_seen TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL,
                    movie_id INTEGER NOT NULL,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, movie_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_favorites_user_added
                    ON favorites(user_id, added_at DESC);
                """
            )
            conn.commit()

    def upsert_user(self, user_id: int, username: str | None):
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO users(user_id, username) VALUES(?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                   last_seen=CURRENT_TIMESTAMP""",
                (user_id, username),
            )
            conn.commit()

    def add_favorite(self, user_id: int, movie_id: int):
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO favorites(user_id, movie_id) VALUES(?, ?)",
                (user_id, movie_id),
            )
            conn.commit()

    def remove_favorite(self, user_id: int, movie_id: int):
        with closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM favorites WHERE user_id=? AND movie_id=?",
                (user_id, movie_id),
            )
            conn.commit()

    def is_favorite(self, user_id: int, movie_id: int) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND movie_id=?",
                (user_id, movie_id),
            ).fetchone()
            return row is not None

    def get_favorites(self, user_id: int, limit: int = 20):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT movie_id FROM favorites WHERE user_id=? ORDER BY added_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [row[0] for row in rows]

    def count_users(self) -> int:
        with closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def count_favorites(self) -> int:
        with closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0])
