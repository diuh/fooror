import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    telegram_token: str
    anthropic_api_key: str
    allowed_chat_id: int | None
    database_path: str
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None
    google_calendar_id: str = "primary"

    @property
    def persistence_path(self) -> str:
        """Pickle file for PTB persistence, kept next to the DB so it lives on
        the same Railway Volume and survives restarts/redeploys."""
        return os.path.join(os.path.dirname(self.database_path) or ".", "bot_state.pkl")

    @property
    def google_enabled(self) -> bool:
        """True when all OAuth creds are present, so Calendar features can run.
        The bot still works without them — meeting scheduling is just disabled."""
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.google_refresh_token
        )

    @classmethod
    def from_env(cls) -> "Config":
        raw_id = os.environ.get("ALLOWED_CHAT_ID")
        return cls(
            telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            allowed_chat_id=int(raw_id) if raw_id else None,
            database_path=os.environ.get("DATABASE_PATH", "data/mentor.db"),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID"),
            google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
            google_refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
            google_calendar_id=os.environ.get("GOOGLE_CALENDAR_ID", "primary"),
        )


config = Config.from_env()
