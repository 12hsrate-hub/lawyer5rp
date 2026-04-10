from __future__ import annotations

import unittest

from shared.ogp_builders import build_bbcode, build_rehab_bbcode
from shared.ogp_models import Representative, Victim
from shared.ogp_types import ComplaintInput, RehabInput


class BbcodeSnapshotTests(unittest.TestCase):
    def test_complaint_bbcode_snapshot(self):
        data = ComplaintInput(
            appeal_no="1234",
            org="LSPD",
            subject_names="John Doe",
            situation_description="Описание событий",
            violation_short="Нарушение",
            event_dt="08.04.2026 14:30",
            today_date="08.04.2026",
            representative=Representative(
                name="Rep Name",
                passport="AA123",
                address="Addr",
                phone="1234567",
                discord="rep",
                passport_scan_url="https://example.com/rep",
            ),
            victim=Victim(
                name="Victim Name",
                passport="BB123",
                address="Addr",
                phone="7654321",
                discord="victim",
                passport_scan_url="https://example.com/victim",
            ),
            evidence_items=[
                ("Договор на оказание юридических услуг", "https://example.com/contract"),
                ("Видеофиксация процессуальных действий: первая часть записи", "https://example.com/video-1"),
            ],
        )

        expected = """[RIGHT][I]To: Attorney General's office,
San-Andreas, Burton, Eastbourne Way,
Dear Attorney General Konstantin Belonozhkin,[/I][/RIGHT]

[CENTER]
[SIZE=5]Обращение №1234[/SIZE]
Я, гражданин штата Сан-Андреас Rep Name, являясь законным представителем гражданина Victim Name и в его интересах, обращаюсь к Вам с просьбой рассмотреть следующую ситуацию и принять необходимые меры в соответствии с законом:
[/CENTER]

[B]Суть обращения:[/B]
[LIST=1]
[*]Организация, в которой состоит объект заявления: LSPD
[*]Объект заявления (имя и фамилия, удостоверение, бейджик, нашивка, жетон): John Doe
[*]Подробное описание ситуации: Описание событий
[*]Формулировка сути нарушения: Нарушение
[*]Дата и время описываемых событий: 08.04.2026 14:30
[*]Доказательства: [URL='https://example.com/contract']Договор на оказание юридических услуг[/URL], [URL='https://example.com/video-1']Видеофиксация процессуальных действий: первая часть записи[/URL].
[/LIST]

[B]Информация о представителе:[/B]
[LIST=1]
[*]Имя, фамилия: Rep Name
[*]Номер паспорта: AA123
[*]Адрес проживания: Addr
[*]Номер телефона: 123-45-67
[*]Адрес электронной почты (( discord )): [EMAIL]rep@sa.com[/EMAIL]
[*]Ксерокопия паспорта (( imgur.com )): [URL='https://example.com/rep']Паспорт[/URL]
[/LIST]

[B]Информация о потерпевшем:[/B]
[LIST=1]
[*]Имя, фамилия: Victim Name
[*]Номер паспорта: BB123
[*]Адрес проживания: Addr
[*]Номер телефона: 765-43-21
[*]Адрес электронной почты (( discord )): [EMAIL]victim@sa.com[/EMAIL]
[*]Ксерокопия паспорта (( imgur.com )): [URL='https://example.com/victim']Паспорт[/URL]
[/LIST]

[RIGHT][/RIGHT]
[B][FONT=trebuchet ms]Дата: [/FONT][/B][FONT=trebuchet ms][U]08.04.2026 г.[/U][/FONT]
[B][FONT=trebuchet ms]Подпись: Rep Name[/FONT][/B]
"""
        self.assertEqual(build_bbcode(data), expected)

    def test_rehab_bbcode_snapshot(self):
        data = RehabInput(
            representative=Representative(
                name="Rep Name",
                passport="AA123",
                address="Addr",
                phone="1234567",
                discord="rep",
                passport_scan_url="https://example.com/rep",
            ),
            principal_name="Victim Name",
            principal_passport="BB123",
            principal_passport_scan_url="https://example.com/principal",
            served_seven_days=True,
            contract_url="https://example.com/contract",
            today_date="08.04.2026",
        )

        expected = """[RIGHT]От гражданина штата Сан-Андреас: Rep Name
в Суд штата Сан-Андреас[/RIGHT]
[CENTER]
[B]ЗАЯВЛЕНИЕ[/B]
[/CENTER]
Я, Rep Name, являясь законным представителем Victim Name, от лица такового, прошу рассмотреть прошение на юридическую реабилитацию. Прошу аннулировать все статьи, содержащиеся в базе данных судимостей в отношении моего доверителя. Подтверждаю, что доверитель выдержал испытательный срок 7 дней с момента последней судимости.

К заявлению прикладываю следующую документацию:
[LIST=1]
[*]Ксерокопия Вашего паспорта, номер паспорта: [URL='https://example.com/rep']ссылка[/URL], AA123;
[*]Ксерокопия паспорта доверителя, номер паспорта доверителя: [URL='https://example.com/principal']ссылка[/URL], BB123;
[*]Копия договора о предоставлении услуг: [URL='https://example.com/contract']копия[/URL];
[*]Контакты: тел. 123-45-67, почта (( discord с #0000 )) [EMAIL]rep@sa.com[/EMAIL].
[/LIST]
Дата подачи заявления: 08.04.2026.
Подпись: Rep Name"""
        self.assertEqual(build_rehab_bbcode(data), expected)


if __name__ == "__main__":
    unittest.main()
