from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: list[int] = []

    marzban_url: str
    marzban_username: str
    marzban_password: str
    marzban_inbound: str = "VLESS TCP REALITY"

    db_path: str = "data/bot.db"
    trial_days: int = 3
    support_username: str = ""
