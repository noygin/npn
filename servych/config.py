from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сайта. Читаются из того же .env, что и у бота."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Токен бота нужен для входа через Telegram и сообщений клиентам
    bot_token: str = ""
    # Username бота без @. Если пусто, узнаём его у Telegram по токену
    servych_bot_username: str = ""
    admin_ids: list[int] = []
    support_username: str = ""

    servych_db_path: str = "data/servych.db"
    servych_host: str = "0.0.0.0"
    servych_port: int = 8088
    # Адрес сайта снаружи, например https://servych.ru. Нужен для кнопки в боте
    servych_public_url: str = ""
    # Включить, когда у сайта появится HTTPS
    servych_secure_cookies: bool = False

    # Цена за месяц в рублях
    servych_price_rub: int = 790
    # Цена за месяц в Telegram Stars
    servych_price_stars: int = 500
    # Токен Crypto Pay (@CryptoBot → Crypto Pay → Создать приложение)
    cryptobot_token: str = ""
    cryptobot_api: str = "https://pay.crypt.bot/api"
