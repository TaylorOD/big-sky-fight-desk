import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Denver")


def now():
    return datetime.now(ZONE).isoformat(timespec="seconds")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def folder(self, episode_id):
        if not re.fullmatch(r"[a-f0-9]{12}", episode_id):
            raise ValueError("Invalid episode ID.")
        return self.root / episode_id

    def create(self, brief):
        episode_id = uuid.uuid4().hex[:12]
        episode = {"id": episode_id, "created_at": now(), "brief": brief.model_dump(mode="json"),
                   "status": "new", "approved": False, "error": None, "log": []}
        self.save(episode)
        return episode

    def save(self, episode):
        write_json(self.folder(episode["id"]) / "episode.json", episode)

    def get(self, episode_id):
        path = self.folder(episode_id) / "episode.json"
        if not path.exists():
            raise ValueError("Episode not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def all(self):
        return sorted([json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*/episode.json")],
                      key=lambda e: e["created_at"], reverse=True)


class Budget:
    # Conservative app allowances, not an exact invoice calculation.
    COSTS = {"research": 0.20, "evidence": 0.08, "draft": 0.08, "review": 0.08,
             "audio": 0.20, "cover": 0.25}

    def __init__(self, path: Path, daily=2.0, monthly=10.0):
        self.path, self.daily, self.monthly = path, daily, monthly
        if not (0 < daily <= 100 and 0 < monthly <= 1000):
            raise ValueError("Allowances must be positive and finite.")
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reservations (at TEXT, episode TEXT, operation TEXT, amount REAL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=20)

    def usage(self, db=None):
        today = now()[:10]
        if db is None:
            with self.connect() as connection:
                return self.usage(connection)
        daily = db.execute("SELECT COALESCE(SUM(amount),0) FROM reservations WHERE substr(at,1,10)=?", (today,)).fetchone()[0]
        monthly = db.execute("SELECT COALESCE(SUM(amount),0) FROM reservations WHERE substr(at,1,7)=?", (today[:7],)).fetchone()[0]
        return {"daily": round(daily, 2), "monthly": round(monthly, 2),
                "daily_limit": self.daily, "monthly_limit": self.monthly}

    def reserve(self, episode, operation):
        amount = self.COSTS[operation]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            usage = self.usage(db)
            if usage["daily"] + amount > self.daily + 1e-8 or usage["monthly"] + amount > self.monthly + 1e-8:
                raise ValueError("Generation allowance reached. Your work is saved. Resume after the allowance resets.")
            db.execute("INSERT INTO reservations VALUES (?,?,?,?)", (now(), episode, operation, amount))
