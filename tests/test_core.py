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
    sub = Subscription(True, 0, 0, "https://x/sub/s")
    assert labels(keyboards.home(sub, 3, "help"))[:2] == ["Подключиться", "Продлить"]


def test_personal_greeting_matches_username_case_insensitively():
    from bot.config import Settings

    s = Settings(
        bot_token="1:x", panel_url="x", panel_api_token="t", panel_inbound_ids=[1],
        panel_sub_url="y", greetings={"@Friend": ["привет"]},
    )
    assert s.greeting_for("friend") == "привет"
    assert s.greeting_for("other") is None
    assert s.greeting_for(None) is None
