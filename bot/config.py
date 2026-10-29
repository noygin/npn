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
