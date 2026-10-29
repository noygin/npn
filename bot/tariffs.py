from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str
    title: str
    days: int
    stars: int


TARIFFS: dict[str, Tariff] = {
    t.code: t
    for t in (
        Tariff("m1", "1 месяц", 30, 150),
        Tariff("m3", "3 месяца", 90, 400),
        Tariff("m6", "6 месяцев", 180, 750),
    )
}
