from bot.panel import DAY, client_email, compute_expire
from bot.tariffs import TARIFFS


def test_new_subscription_starts_now():
    assert compute_expire(None, 1000, 3) == 1000 + 3 * DAY


def test_active_subscription_is_extended_from_its_end():
    assert compute_expire(5000, 1000, 30) == 5000 + 30 * DAY


def test_expired_subscription_restarts_from_now():
    assert compute_expire(500, 1000, 30) == 1000 + 30 * DAY


def test_client_email_is_valid():
    name = client_email(123456789)
    assert 3 <= len(name) <= 32 and name.isalnum()


def test_tariff_codes_fit_invoice_payload():
    for code, t in TARIFFS.items():
        assert code == t.code and t.days > 0 and t.stars > 0


def test_plural_days():
    from bot.texts import plural_days

    assert [plural_days(n) for n in (1, 3, 5, 11, 21, 22, 30)] == [
        "1 день", "3 дня", "5 дней", "11 дней", "21 день", "22 дня", "30 дней",
    ]


def test_home_keyboard_offers_trial_only_without_subscription():
    from bot import keyboards
    from bot.panel import Subscription

    def labels(kb):
        return [b.text for row in kb.inline_keyboard for b in row]

    assert "Попробовать 3 дня бесплатно" in labels(keyboards.home(None, 3, ""))
    assert not any("бесплатно" in t for t in labels(keyboards.home(None, None, "")))
    sub = Subscription(True, 2_000_000_000, 0, "https://x/sub/s")
    assert labels(keyboards.home(sub, 3, "help"))[:2] == ["Подключиться", "Продлить"]
    unlimited = Subscription(True, 0, 0, "https://x/sub/s")
    assert "Продлить" not in labels(keyboards.home(unlimited, 3, ""))


def test_personal_greeting_matches_username_case_insensitively():
    from bot.config import Settings

    s = Settings(
        bot_token="1:x", panel_url="x", panel_api_token="t", panel_inbound_ids=[1],
        panel_sub_url="y", greetings={"@Friend": ["привет"]},
    )
    assert s.greeting_for("friend") == "привет"
    assert s.greeting_for("other") is None
    assert s.greeting_for(None) is None


def test_free_users():
    from bot.config import Settings

    s = Settings(
        bot_token="1:x", panel_url="x", panel_api_token="t", panel_inbound_ids=[1],
        panel_sub_url="y", free_users=["@Friend"],
    )
    assert s.is_free("friend") and not s.is_free("other") and not s.is_free(None)


def test_parse_duration():
    from bot.handlers.admin import parse_duration

    assert parse_duration(None) == 30
    assert parse_duration("7") == 7
    assert parse_duration("Навсегда") is None
    assert parse_duration("0") is False and parse_duration("abc") is False


def test_reminder_kind():
    from bot.reminders import reminder_kind

    now = 1_000_000
    assert reminder_kind(0, now) is None
    assert reminder_kind(now + 3 * DAY, now) is None
    assert reminder_kind(now + DAY // 2, now) == "soon"
    assert reminder_kind(now - 10, now) == "ended"
    assert reminder_kind(now - 3 * DAY, now) is None


def test_tg_id_from_email():
    from bot.panel import tg_id_from_email

    assert tg_id_from_email("tg123") == 123
    assert tg_id_from_email("main") is None and tg_id_from_email("tgx") is None


def test_parse_referrer():
    from bot.handlers.menu import parse_referrer

    assert parse_referrer("ref123") == 123
    assert parse_referrer(None) is None
    assert parse_referrer("refx") is None and parse_referrer("123") is None


def test_parse_promo():
    from bot.handlers.admin import parse_promo

    assert parse_promo("friends 14 50") == ("FRIENDS", 14, 50)
    assert parse_promo("gift 7") == ("GIFT", 7, 1)
    assert parse_promo("x 7") is None and parse_promo("gift 0") is None
    assert parse_promo("gift seven") is None
