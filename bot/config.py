import random

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: list[int] = []

    # Адрес панели 3x-ui вместе с webBasePath, например https://1.2.3.4:48453/secret
    panel_url: str
    panel_api_token: str
    panel_inbound_ids: list[int]
    # Начало ссылки-подписки, например https://1.2.3.4:2096/sub
    panel_sub_url: str

    db_path: str = "data/bot.db"
    trial_days: int = 3
    support_username: str = ""
    # Личные приветствия: {"username": ["фраза", ...]}, username без @
    greetings: dict[str, list[str]] = {}
    # Пользователи с бесплатной бессрочной подпиской, username без @
    free_users: list[str] = []

    def is_free(self, username: str | None) -> bool:
        return bool(username) and username.lower() in {
            u.lower().lstrip("@") for u in self.free_users
        }

    def greeting_for(self, username: str | None) -> str | None:
        phrases = {k.lower().lstrip("@"): v for k, v in self.greetings.items()}.get(
            (username or "").lower()
        )
        return random.choice(phrases) if phrases else None
