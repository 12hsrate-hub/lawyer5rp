from __future__ import annotations

import warnings

from shared.ogp_formatting import (
    build_evidence_line,
    escape_bbcode_text,
    format_phone_for_bbcode,
    normalize_discord_to_email,
    sanitize_url,
)
from shared.ogp_types import ComplaintInput, RehabInput


def build_bbcode(data: ComplaintInput) -> str:
    evidence_line = build_evidence_line(data.evidence_items)
    rep_email = escape_bbcode_text(normalize_discord_to_email(data.representative.discord))
    vic_email = escape_bbcode_text(normalize_discord_to_email(data.victim.discord))
    rep_scan_url = sanitize_url(data.representative.passport_scan_url)
    victim_scan_url = sanitize_url(data.victim.passport_scan_url)
    representative_phone = escape_bbcode_text(format_phone_for_bbcode(data.representative.phone))
    victim_phone = escape_bbcode_text(format_phone_for_bbcode(data.victim.phone))

    return f"""[RIGHT][I]To: Attorney General's office,
San-Andreas, Burton, Eastbourne Way,
Dear Attorney General Konstantin Belonozhkin,[/I][/RIGHT]

[CENTER]
[SIZE=5]Обращение №{escape_bbcode_text(data.appeal_no)}[/SIZE]
Я, гражданин штата Сан-Андреас {escape_bbcode_text(data.representative.name)}, являясь законным представителем гражданина {escape_bbcode_text(data.victim.name)} и в его интересах, обращаюсь к Вам с просьбой рассмотреть следующую ситуацию и принять необходимые меры в соответствии с законом:
[/CENTER]

[B]Суть обращения:[/B]
[LIST=1]
[*]Организация, в которой состоит объект заявления: {escape_bbcode_text(data.org)}
[*]Объект заявления (имя и фамилия, удостоверение, бейджик, нашивка, жетон): {escape_bbcode_text(data.subject_names)}
[*]Подробное описание ситуации: {escape_bbcode_text(data.situation_description)}
[*]Формулировка сути нарушения: {escape_bbcode_text(data.violation_short)}
[*]Дата и время описываемых событий: {escape_bbcode_text(data.event_dt)}
[*]Доказательства: {evidence_line}
[/LIST]

[B]Информация о представителе:[/B]
[LIST=1]
[*]Имя, фамилия: {escape_bbcode_text(data.representative.name)}
[*]Номер паспорта: {escape_bbcode_text(data.representative.passport)}
[*]Адрес проживания: {escape_bbcode_text(data.representative.address)}
[*]Номер телефона: {representative_phone}
[*]Адрес электронной почты (( discord )): [EMAIL]{rep_email}[/EMAIL]
[*]Ксерокопия паспорта (( imgur.com )): [URL='{rep_scan_url}']Паспорт[/URL]
[/LIST]

[B]Информация о потерпевшем:[/B]
[LIST=1]
[*]Имя, фамилия: {escape_bbcode_text(data.victim.name)}
[*]Номер паспорта: {escape_bbcode_text(data.victim.passport)}
[*]Адрес проживания: {escape_bbcode_text(data.victim.address)}
[*]Номер телефона: {victim_phone}
[*]Адрес электронной почты (( discord )): [EMAIL]{vic_email}[/EMAIL]
[*]Ксерокопия паспорта (( imgur.com )): [URL='{victim_scan_url}']Паспорт[/URL]
[/LIST]

[RIGHT][/RIGHT]
[B][FONT=trebuchet ms]Дата: [/FONT][/B][FONT=trebuchet ms][U]{escape_bbcode_text(data.today_date)} г.[/U][/FONT]
[B][FONT=trebuchet ms]Подпись: {escape_bbcode_text(data.representative.name)}[/FONT][/B]
"""


def build_rehab_bbcode(data: RehabInput) -> str:
    representative_phone = escape_bbcode_text(format_phone_for_bbcode(data.representative.phone))
    representative_contact = escape_bbcode_text(normalize_discord_to_email(data.representative.discord))
    rep_scan_url = sanitize_url(data.representative.passport_scan_url)
    principal_scan_url = sanitize_url(data.principal_passport_scan_url)
    served_text = (
        "Подтверждаю, что доверитель выдержал испытательный срок 7 дней с момента последней судимости."
        if data.served_seven_days
        else ""
    )
    served_suffix = f" {served_text}" if served_text else ""

    return f"""[RIGHT]От гражданина штата Сан-Андреас: {escape_bbcode_text(data.representative.name)}
в Суд штата Сан-Андреас[/RIGHT]
[CENTER]
[B]ЗАЯВЛЕНИЕ[/B]
[/CENTER]
Я, {escape_bbcode_text(data.representative.name)}, являясь законным представителем {escape_bbcode_text(data.principal_name)}, от лица такового, прошу рассмотреть прошение на юридическую реабилитацию. Прошу аннулировать все статьи, содержащиеся в базе данных судимостей в отношении моего доверителя.{served_suffix}

К заявлению прикладываю следующую документацию:
[LIST=1]
[*]Ксерокопия Вашего паспорта, номер паспорта: [URL='{rep_scan_url}']ссылка[/URL], {escape_bbcode_text(data.representative.passport)};
[*]Ксерокопия паспорта доверителя, номер паспорта доверителя: [URL='{principal_scan_url}']ссылка[/URL], {escape_bbcode_text(data.principal_passport)};
[*]Копия договора о предоставлении услуг: [URL='{sanitize_url(data.contract_url)}']копия[/URL];
[*]Контакты: тел. {representative_phone}, почта (( discord с #0000 )) [EMAIL]{representative_contact}[/EMAIL].
[/LIST]
Дата подачи заявления: {escape_bbcode_text(data.today_date)}.
Подпись: {escape_bbcode_text(data.representative.name)}"""


def build_ai_prompt(
    legal_reference: str,
    victim_name: str,
    org: str,
    subject: str,
    event_dt: str,
    raw_desc: str,
) -> str:
    warnings.warn(
        "build_ai_prompt is deprecated and kept only for backward compatibility. "
        "Use shared.ogp_ai_prompts.build_suggest_prompt instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return f"""
Ты юридический помощник по жалобам GTA5RP в Офис Генерального прокурора.
Жалоба подаётся адвокатом в интересах доверителя. Нужно переписать только описательную часть жалобы, то есть пункт 3, в нейтральном, деловом и связном стиле.

При анализе опирайся только на следующие правовые источники и их статьи:
{legal_reference}

Что нужно сделать:
- перепиши только пункт 3;
- сохраняй процессуальную роль: текст должен выглядеть как изложение адвоката, действующего в интересах доверителя;
- не добавляй BBCode, заголовки, списки и служебные пометки;
- не придумывай новых фактов, используй только то, что есть в черновике;
- если в черновике есть номер запроса, укажи его в описательной части;
- если в черновике есть номер договора, укажи его;
- дату подписания договора указывай только если такая дата прямо есть в черновике;
- если из описания усматриваются нарушения, аккуратно укажи в тексте на релевантные статьи кодексов;
- если конкретную статью нельзя уверенно определить по фактам, не выдумывай ее;
- не придумывай номер запроса, номер договора или дату договора, если их нет в исходном тексте;
- итоговый текст должен быть готов для вставки в пункт 3 жалобы.

Требования к результату:
- один связный текст без маркированных списков;
- официальный и нейтральный тон;
- допустимо ссылаться на статьи в формате: "что может указывать на нарушение требований ст. ...";
- основной акцент на фактах, затем на правовой опоре;
- если подходят несколько статей, упоминай только действительно релевантные;
- не превращай пункт 3 в отдельное правовое заключение, он должен оставаться именно описательной частью жалобы.

Данные жалобы:
Потерпевший/доверитель: {victim_name}
Организация объекта жалобы: {org}
Объект заявления: {subject}
Дата и время события: {event_dt}

Черновик пункта 3:
{raw_desc}
    """.strip()
