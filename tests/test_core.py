from bot.marzban import DAY, compute_expire, marzban_username
from bot.tariffs import TARIFFS


def test_new_subscription_starts_now():
    assert compute_expire(None, 1000, 3) == 1000 + 3 * DAY


def test_active_subscription_is_extended_from_its_end():
    assert compute_expire(5000, 1000, 30) == 5000 + 30 * DAY


def test_expired_subscription_restarts_from_now():
    assert compute_expire(500, 1000, 30) == 1000 + 30 * DAY


def test_marzban_username_is_valid():
    name = marzban_username(123456789)
    assert 3 <= len(name) <= 32 and name.isalnum()


def test_tariff_codes_fit_invoice_payload():
    for code, t in TARIFFS.items():
        assert code == t.code and t.days > 0 and t.stars > 0
