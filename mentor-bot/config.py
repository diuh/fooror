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

    @property
    def persistence_path(self) -> str:
        """Pickle file for PTB persistence, kept next to the DB so it lives on
        the same Railway Volume and survives restarts/redeploys."""
        return os.path.join(os.path.dirname(self.database_path) or ".", "bot_state.pkl")

    @classmethod
    def from_env(cls) -> "Config":
        raw_id = os.environ.get("ALLOWED_CHAT_ID")
        return cls(
            telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            allowed_chat_id=int(raw_id) if raw_id else None,
            database_path=os.environ.get("DATABASE_PATH", "data/mentor.db"),
        )


config = Config.from_env()
