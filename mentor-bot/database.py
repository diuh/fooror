import json
import os
import aiosqlite
import contextlib
from datetime import datetime, date
from typing import Any

from config import config


@contextlib.asynccontextmanager
async def get_db():
    os.makedirs(os.path.dirname(config.database_path), exist_ok=True)
    db = await aiosqlite.connect(config.database_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    async with get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS leads (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                company          TEXT,
                contact          TEXT,
                project_type     TEXT,
                estimated_value  REAL,
                actual_value     REAL,
                status           TEXT NOT NULL DEFAULT 'new'
                                 CHECK(status IN ('new','negotiation','proposal','closed','rejected')),
                source           TEXT,
                notes            TEXT,
                next_action      TEXT,
                next_action_date TEXT,
                created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at        TEXT
            );

            CREATE TABLE IF NOT EXISTS income_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id      INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                amount       REAL NOT NULL,
                payment_date TEXT NOT NULL,
                month        TEXT NOT NULL,
                description  TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date        TEXT NOT NULL,
                log_type        TEXT NOT NULL CHECK(log_type IN ('morning','evening')),
                raw_input       TEXT,
                tasks_planned   TEXT,
                tasks_done      TEXT,
                leads_contacted INTEGER DEFAULT 0,
                proposals_sent  INTEGER DEFAULT 0,
                mood_score      INTEGER,
                ai_response     TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS content_ideas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform     TEXT NOT NULL CHECK(platform IN ('linkedin','behance','telegram','instagram')),
                title        TEXT NOT NULL,
                body         TEXT,
                status       TEXT NOT NULL DEFAULT 'idea'
                             CHECK(status IN ('idea','draft','scheduled','published')),
                publish_date TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS proposals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id        INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                project_type   TEXT NOT NULL,
                scope_summary  TEXT,
                price_low      REAL,
                price_high     REAL,
                timeline_weeks INTEGER,
                proposal_text  TEXT,
                status         TEXT NOT NULL DEFAULT 'draft'
                               CHECK(status IN ('draft','sent','accepted','rejected')),
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                task_date  TEXT NOT NULL,
                title      TEXT NOT NULL,
                done       INTEGER NOT NULL DEFAULT 0,
                source     TEXT NOT NULL DEFAULT 'ai'
                           CHECK(source IN ('ai','user')),
                horizon    TEXT NOT NULL DEFAULT 'day'
                           CHECK(horizon IN ('day','week','month')),
                period_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                done_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS monthly_plans (
                month      TEXT PRIMARY KEY,
                goal       REAL,
                rationale  TEXT,
                survey     TEXT,
                analysis   TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                gcal_event_id TEXT,
                title         TEXT NOT NULL,
                start_utc     TEXT NOT NULL,
                end_utc       TEXT NOT NULL,
                is_online     INTEGER NOT NULL DEFAULT 0,
                location      TEXT,
                meet_link     TEXT,
                attendees     TEXT,
                html_link     TEXT,
                reminded_1h   INTEGER NOT NULL DEFAULT 0,
                reminded_5m   INTEGER NOT NULL DEFAULT 0,
                canceled      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads(status);
            CREATE INDEX IF NOT EXISTS idx_income_month    ON income_log(month);
            CREATE INDEX IF NOT EXISTS idx_daily_logs_date ON daily_logs(log_date, log_type);
            CREATE INDEX IF NOT EXISTS idx_tasks_date      ON tasks(task_date);
            CREATE INDEX IF NOT EXISTS idx_meetings_start  ON meetings(start_utc);
        """)

        # Migration: add horizon/period_key to pre-existing tasks tables and
        # backfill day-level rows (period_key = task_date) so older DBs upgrade
        # cleanly on Railway without losing data.
        async with db.execute("PRAGMA table_info(tasks)") as cur:
            cols = {r["name"] for r in await cur.fetchall()}
        if "horizon" not in cols:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN horizon TEXT NOT NULL DEFAULT 'day'"
            )
        if "period_key" not in cols:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN period_key TEXT NOT NULL DEFAULT ''"
            )
            await db.execute(
                "UPDATE tasks SET period_key = task_date WHERE period_key = ''"
            )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_period ON tasks(horizon, period_key)"
        )

        await db.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES (?, ?)",
            ("monthly_goal", "10000"),
        )
        await db.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES (?, ?)",
            ("timezone", "Europe/Kyiv"),
        )
        await db.commit()


# ── Config ────────────────────────────────────────────────────────────────────

async def get_config(key: str) -> str | None:
    async with get_db() as db:
        async with db.execute("SELECT value FROM config WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row["value"] if row else None


async def set_config(key: str, value: str) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES (?, ?)", (key, value)
        )
        await db.commit()


# ── Income ────────────────────────────────────────────────────────────────────

async def add_income(amount: float, description: str, payment_date: str | None = None, lead_id: int | None = None) -> int:
    pd = payment_date or date.today().isoformat()
    month = pd[:7]
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO income_log(lead_id, amount, payment_date, month, description) VALUES (?,?,?,?,?)",
            (lead_id, amount, pd, month, description),
        )
        await db.commit()
        return cur.lastrowid


async def get_month_income(month: str | None = None) -> float:
    m = month or date.today().strftime("%Y-%m")
    async with get_db() as db:
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) as total FROM income_log WHERE month = ?", (m,)
        ) as cur:
            row = await cur.fetchone()
            return float(row["total"])


async def get_income_history(months: int = 6) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT month, SUM(amount) as total, COUNT(*) as n_payments
            FROM income_log
            GROUP BY month
            ORDER BY month DESC
            LIMIT ?
            """,
            (months,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_recent_income_entries(limit: int = 5) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM income_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Leads ─────────────────────────────────────────────────────────────────────

async def add_lead(
    name: str,
    project_type: str = "",
    estimated_value: float = 0,
    source: str = "",
    company: str = "",
    contact: str = "",
    notes: str = "",
    next_action: str = "",
    next_action_date: str = "",
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO leads
               (name, company, contact, project_type, estimated_value, source, notes, next_action, next_action_date)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (name, company, contact, project_type, estimated_value, source, notes, next_action, next_action_date),
        )
        await db.commit()
        return cur.lastrowid


async def get_leads(status: str | None = None) -> list[dict]:
    async with get_db() as db:
        if status:
            async with db.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY updated_at DESC", (status,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM leads WHERE status NOT IN ('closed','rejected') ORDER BY updated_at DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


async def get_lead(lead_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_lead(lead_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    if fields.get("status") in ("closed", "rejected") and "closed_at" not in fields:
        fields["closed_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [lead_id]
    async with get_db() as db:
        await db.execute(f"UPDATE leads SET {set_clause} WHERE id = ?", values)
        await db.commit()


async def get_pipeline_summary() -> dict:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT status,
                   COUNT(*) as n,
                   COALESCE(SUM(estimated_value),0) as total_value
            FROM leads
            GROUP BY status
            """
        ) as cur:
            rows = await cur.fetchall()
            result = {r["status"]: {"n": r["n"], "value": float(r["total_value"])} for r in rows}
            return result


async def get_overdue_leads() -> list[dict]:
    today = date.today().isoformat()
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM leads
               WHERE next_action_date < ? AND next_action_date != ''
               AND status NOT IN ('closed','rejected')
               ORDER BY next_action_date""",
            (today,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Daily Logs ────────────────────────────────────────────────────────────────

async def upsert_daily_log(
    log_date: str,
    log_type: str,
    raw_input: str = "",
    tasks_planned: str = "[]",
    tasks_done: str = "[]",
    leads_contacted: int = 0,
    proposals_sent: int = 0,
    mood_score: int | None = None,
    ai_response: str = "",
) -> None:
    async with get_db() as db:
        existing = await db.execute(
            "SELECT id FROM daily_logs WHERE log_date = ? AND log_type = ?",
            (log_date, log_type),
        )
        row = await existing.fetchone()
        if row:
            await db.execute(
                """UPDATE daily_logs SET raw_input=?, tasks_planned=?, tasks_done=?,
                   leads_contacted=?, proposals_sent=?, mood_score=?, ai_response=?
                   WHERE log_date=? AND log_type=?""",
                (raw_input, tasks_planned, tasks_done, leads_contacted, proposals_sent,
                 mood_score, ai_response, log_date, log_type),
            )
        else:
            await db.execute(
                """INSERT INTO daily_logs
                   (log_date, log_type, raw_input, tasks_planned, tasks_done,
                    leads_contacted, proposals_sent, mood_score, ai_response)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (log_date, log_type, raw_input, tasks_planned, tasks_done,
                 leads_contacted, proposals_sent, mood_score, ai_response),
            )
        await db.commit()


async def get_daily_log(log_date: str, log_type: str) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM daily_logs WHERE log_date = ? AND log_type = ?",
            (log_date, log_type),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_checkin_history(days: int = 7) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM daily_logs ORDER BY log_date DESC, log_type DESC LIMIT ?",
            (days * 2,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_streak() -> int:
    async with get_db() as db:
        async with db.execute(
            """SELECT DISTINCT log_date FROM daily_logs
               WHERE log_type = 'evening'
               ORDER BY log_date DESC"""
        ) as cur:
            rows = await cur.fetchall()

    streak = 0
    today = date.today()
    for i, row in enumerate(rows):
        expected = (today - __import__("datetime").timedelta(days=i)).isoformat()
        if row["log_date"] == expected:
            streak += 1
        else:
            break
    return streak


# ── Content Ideas ─────────────────────────────────────────────────────────────

async def add_content_idea(platform: str, title: str, body: str = "", publish_date: str = "") -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO content_ideas(platform, title, body, publish_date) VALUES (?,?,?,?)",
            (platform, title, body, publish_date),
        )
        await db.commit()
        return cur.lastrowid


async def get_content_ideas(platform: str | None = None, status: str | None = None) -> list[dict]:
    async with get_db() as db:
        conditions = []
        params = []
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        async with db.execute(
            f"SELECT * FROM content_ideas {where} ORDER BY created_at DESC LIMIT 20",
            params,
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Proposals ─────────────────────────────────────────────────────────────────

async def add_proposal(
    project_type: str,
    scope_summary: str,
    price_low: float,
    price_high: float,
    timeline_weeks: int,
    proposal_text: str,
    lead_id: int | None = None,
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO proposals
               (lead_id, project_type, scope_summary, price_low, price_high, timeline_weeks, proposal_text)
               VALUES (?,?,?,?,?,?,?)""",
            (lead_id, project_type, scope_summary, price_low, price_high, timeline_weeks, proposal_text),
        )
        await db.commit()
        return cur.lastrowid


# ── Tasks ─────────────────────────────────────────────────────────────────────

async def add_task(period_key: str, title: str, source: str = "ai", horizon: str = "day") -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO tasks(task_date, title, source, horizon, period_key) VALUES (?,?,?,?,?)",
            (period_key, title, source, horizon, period_key),
        )
        await db.commit()
        return cur.lastrowid


async def add_tasks(period_key: str, titles: list[str], source: str = "ai", horizon: str = "day") -> None:
    async with get_db() as db:
        await db.executemany(
            "INSERT INTO tasks(task_date, title, source, horizon, period_key) VALUES (?,?,?,?,?)",
            [(period_key, t, source, horizon, period_key) for t in titles],
        )
        await db.commit()


async def get_tasks(period_key: str, horizon: str = "day") -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tasks WHERE period_key = ? AND horizon = ? ORDER BY id",
            (period_key, horizon),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_pending_tasks(period_key: str, horizon: str = "day") -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tasks WHERE period_key = ? AND horizon = ? AND done = 0 ORDER BY id",
            (period_key, horizon),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_task(task_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def toggle_task(task_id: int) -> bool:
    """Flip a task's done state. Returns the new done state."""
    async with get_db() as db:
        async with db.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return False
        new_done = 0 if row["done"] else 1
        done_at = datetime.now().isoformat() if new_done else None
        await db.execute(
            "UPDATE tasks SET done = ?, done_at = ? WHERE id = ?",
            (new_done, done_at, task_id),
        )
        await db.commit()
        return bool(new_done)


async def delete_tasks_for_period(period_key: str, horizon: str = "day", source: str | None = None) -> None:
    async with get_db() as db:
        if source:
            await db.execute(
                "DELETE FROM tasks WHERE period_key = ? AND horizon = ? AND source = ?",
                (period_key, horizon, source),
            )
        else:
            await db.execute(
                "DELETE FROM tasks WHERE period_key = ? AND horizon = ?",
                (period_key, horizon),
            )
        await db.commit()


async def replace_tasks(period_key: str, titles: list[str], horizon: str = "day") -> None:
    """Replace a period's task list, preserving the done-state of any task whose
    title is unchanged (case-insensitive). Used when editing a plan via free
    text so already-completed items are not silently reset."""
    async with get_db() as db:
        async with db.execute(
            "SELECT title, done, done_at FROM tasks WHERE period_key = ? AND horizon = ?",
            (period_key, horizon),
        ) as cur:
            prev = {
                r["title"].strip().lower(): (r["done"], r["done_at"])
                for r in await cur.fetchall()
            }
        await db.execute(
            "DELETE FROM tasks WHERE period_key = ? AND horizon = ?", (period_key, horizon)
        )
        for title in titles:
            done, done_at = prev.get(title.strip().lower(), (0, None))
            await db.execute(
                "INSERT INTO tasks(task_date, title, source, horizon, period_key, done, done_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (period_key, title, "ai", horizon, period_key, done, done_at),
            )
        await db.commit()


async def delete_task(task_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()


async def get_month_task_stats(month: str) -> dict:
    """Completion stats for day-level tasks in a YYYY-MM month. Week/month
    horizon rows are excluded so higher levels don't double-count."""
    async with get_db() as db:
        async with db.execute(
            """SELECT COUNT(*) as total, COALESCE(SUM(done),0) as done
               FROM tasks WHERE horizon = 'day' AND substr(period_key,1,7) = ?""",
            (month,),
        ) as cur:
            row = await cur.fetchone()
            return {"total": row["total"], "done": row["done"]}


# ── Monthly Plans ─────────────────────────────────────────────────────────────

async def save_monthly_plan(month: str, goal: float, rationale: str = "", survey: str = "") -> None:
    async with get_db() as db:
        await db.execute(
            """INSERT INTO monthly_plans(month, goal, rationale, survey)
               VALUES (?,?,?,?)
               ON CONFLICT(month) DO UPDATE SET
                 goal=excluded.goal, rationale=excluded.rationale, survey=excluded.survey""",
            (month, goal, rationale, survey),
        )
        await db.commit()


async def save_month_analysis(month: str, analysis: str) -> None:
    async with get_db() as db:
        await db.execute(
            """INSERT INTO monthly_plans(month, analysis) VALUES (?, ?)
               ON CONFLICT(month) DO UPDATE SET analysis=excluded.analysis""",
            (month, analysis),
        )
        await db.commit()


async def get_monthly_plan(month: str) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM monthly_plans WHERE month = ?", (month,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ── Meetings ──────────────────────────────────────────────────────────────────

async def add_meeting(
    title: str,
    start_utc: str,
    end_utc: str,
    is_online: bool,
    location: str = "",
    meet_link: str = "",
    attendees: str = "",
    html_link: str = "",
    gcal_event_id: str = "",
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """INSERT INTO meetings
               (gcal_event_id, title, start_utc, end_utc, is_online,
                location, meet_link, attendees, html_link)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (gcal_event_id, title, start_utc, end_utc, int(is_online),
             location, meet_link, attendees, html_link),
        )
        await db.commit()
        return cur.lastrowid


async def get_meeting(meeting_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_upcoming_meetings(limit: int = 10) -> list[dict]:
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM meetings
               WHERE canceled = 0 AND start_utc >= ?
               ORDER BY start_utc LIMIT ?""",
            (now, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_meetings_for_reminder() -> list[dict]:
    """Future, non-canceled meetings that still have a pending reminder flag."""
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM meetings
               WHERE canceled = 0 AND start_utc >= ?
               AND (reminded_1h = 0 OR reminded_5m = 0)
               ORDER BY start_utc""",
            (now,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_reminded(meeting_id: int, which: str) -> None:
    column = "reminded_1h" if which == "1h" else "reminded_5m"
    async with get_db() as db:
        await db.execute(
            f"UPDATE meetings SET {column} = 1 WHERE id = ?", (meeting_id,)
        )
        await db.commit()


async def cancel_meeting(meeting_id: int) -> dict | None:
    """Mark a meeting canceled. Returns the row (for deleting from Google)."""
    async with get_db() as db:
        async with db.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
        await db.execute("UPDATE meetings SET canceled = 1 WHERE id = ?", (meeting_id,))
        await db.commit()
        return dict(row)


# ── Context Snapshot ──────────────────────────────────────────────────────────

async def build_context_snapshot() -> dict:
    import datetime as dt

    today = date.today()
    month = today.strftime("%Y-%m")
    days_in_month = (dt.date(today.year + (today.month // 12), (today.month % 12) + 1, 1) - dt.timedelta(days=1)).day
    days_left = days_in_month - today.day

    goal = float(await get_config("monthly_goal") or 10000)
    month_income = await get_month_income(month)
    pct = (month_income / goal * 100) if goal else 0
    daily_pace = ((goal - month_income) / days_left) if days_left > 0 else 0

    pipeline = await get_pipeline_summary()
    overdue = await get_overdue_leads()
    streak = await get_streak()

    morning_log = await get_daily_log(today.isoformat(), "morning")
    evening_log = await get_daily_log(today.isoformat(), "evening")

    recent_income = await get_recent_income_entries(1)
    last_payment = recent_income[0] if recent_income else None

    tasks_today = await get_tasks(today.isoformat())
    tasks_done = sum(1 for t in tasks_today if t["done"])

    return {
        "today": today.isoformat(),
        "month": month,
        "days_left": days_left,
        "goal": goal,
        "month_income": month_income,
        "pct": pct,
        "daily_pace": daily_pace,
        "pipeline": pipeline,
        "overdue_leads": overdue,
        "streak": streak,
        "morning_log": morning_log,
        "evening_log": evening_log,
        "last_payment": last_payment,
        "tasks_today": tasks_today,
        "tasks_done": tasks_done,
        "tasks_total": len(tasks_today),
    }
