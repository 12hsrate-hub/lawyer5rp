from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LawSource:
    title: str
    url: str


BLACKBERRY_LAW_SOURCES: tuple[LawSource, ...] = (
    LawSource("Процессуальный кодекс", "https://forum.gta5rp.com/threads/processualnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826899/"),
    LawSource("Судебные прецеденты", "https://forum.gta5rp.com/threads/sudebnye-precedenty.1291064/"),
    LawSource("Дорожный кодекс", "https://forum.gta5rp.com/threads/dorozhnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2025-goda.826974/"),
    LawSource("Уголовный кодекс", "https://forum.gta5rp.com/threads/ugolovnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826988/"),
    LawSource("Административный кодекс", "https://forum.gta5rp.com/threads/administrativnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2025-goda.827016/"),
    LawSource("Конституция штата", "https://forum.gta5rp.com/threads/konstitucija-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826866/"),
    LawSource("Этический кодекс", "https://forum.gta5rp.com/threads/ehticheskii-kodeks-shtata-san-andreas-redakcija-ot-19-oktjabrja-2024-goda.826971/"),
    LawSource("Закон о региональных правоохранительных органах", "https://forum.gta5rp.com/threads/zakon-o-dejatelnosti-regionalnyx-pravooxranitelnyx-organov-redakcija-ot-29-marta-2026-goda.3284897/"),
    LawSource("Трудовой кодекс", "https://forum.gta5rp.com/threads/trudovoi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.827090/"),
    LawSource("Закон об офисе генерального прокурора", "https://forum.gta5rp.com/threads/zakon-o-dejatelnosti-ofisa-generalnogo-prokurora-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.827354/"),
    LawSource("Закон о FIB", "https://forum.gta5rp.com/threads/zakon-o-federalnom-rassledovatelskom-bjuro-redakcija-ot-29-marta-2026-goda.827363/"),
    LawSource("Закон об адвокатуре", "https://forum.gta5rp.com/threads/zakon-ob-advokature-i-advokatskoi-dejatelnosti-v-shtate-san-andreas-redakcija-ot-05-marta-2026-goda.827351/"),
    LawSource("Закон о национальной гвардии", "https://forum.gta5rp.com/threads/zakon-o-nacionalnoi-gvardii-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.827345/"),
    LawSource("Закон о секретной службе", "https://forum.gta5rp.com/threads/zakon-o-dejatelnosti-sekretnoi-sluzhby-soedinennyx-shtatov-ameriki-v-shtate-san-andreas-redakcija-ot-29-marta-2025-goda.827327/"),
    LawSource("Закон об обороте оружия", "https://forum.gta5rp.com/threads/zakon-o-regulirovanii-oborota-oruzhija-boepripasov-i-specsredstv-v-shtate-san-andreas-redakcija-ot-29-marta-2025-goda.827128/"),
    LawSource("Закон о неприкосновенности госслужащих", "https://forum.gta5rp.com/threads/zakon-ob-obespechenii-neprikosnovennosti-gosudarstvennyx-sluzhaschix-redakcija-ot-05-marta-2026-goda.827114/"),
)


LAW_QA_SOURCES_BY_SERVER: dict[str, tuple[LawSource, ...]] = {
    "blackberry": BLACKBERRY_LAW_SOURCES,
}


def get_law_sources(server_code: str) -> tuple[LawSource, ...]:
    return LAW_QA_SOURCES_BY_SERVER.get(str(server_code or "").strip().lower(), ())

