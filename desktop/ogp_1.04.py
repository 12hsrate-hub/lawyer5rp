from __future__ import annotations

import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtCore import QDateTime
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from shared.ogp_ai import suggest_description_with_proxy_fallback
from shared.ogp_core import (
    ComplaintInput as SharedComplaintInput,
    DEFAULT_SITUATION_PLACEHOLDER,
    DEFAULT_VIOLATION_PLACEHOLDER,
    build_bbcode as shared_build_bbcode,
    collect_evidence_items as shared_collect_evidence_items,
    validate_complaint_input as shared_validate_complaint_input,
)
from ogp_desktop_support import (
    APP_DIR,
    LOGGER,
    LOG_PATH,
    PROFILE_PATH,
    SETTINGS_PATH,
    atomic_write_text,
    is_valid_http_url,
    load_profile,
    load_settings,
    log_exception,
    mask_secret,
    save_profile,
    save_settings,
    write_settings_template,
)
from shared.ogp_models import Representative, Victim


# -------------------- Paths / config --------------------
# ???????????? ?? ???????? .exe:
# py -m pip install -U pyinstaller PySide6 openai httpx
# py -m PyInstaller --noconsole --onefile --collect-all PySide6 ogp_1.03_local_settings.py

APP_VERSION = "1.0.4"
AI_ATTEMPTS_LIMIT = 2
OPENAI_MODEL = "gpt-5.4"
OPENAI_TIMEOUT_SECONDS = 120.0
OPENAI_CONNECT_TIMEOUT_SECONDS = 30.0


# -------------------- Main window --------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OGP Builder - GTA5RP")
        self.resize(980, 920)

        self.rep = load_profile()
        self.settings = load_settings()
        self.ai_attempts_used = 0
        self._openai_client = None
        self._openai_client_signature: tuple[str, str] | None = None

        root = QVBoxLayout(self)
        header = QLabel(
            f"Версия: {APP_VERSION} | Профиль: {PROFILE_PATH} | Настройки: {SETTINGS_PATH} | Лог: {LOG_PATH}"
        )
        header.setWordWrap(True)
        root.addWidget(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.tab_profile = QWidget()
        self.tab_settings = QWidget()
        self.tab_complaint = QWidget()
        self.tabs.addTab(self.tab_profile, "Профиль")
        self.tabs.addTab(self.tab_settings, "Локальные настройки")
        self.tabs.addTab(self.tab_complaint, "Новая жалоба")

        self._build_profile_tab()
        self._build_settings_tab()
        self._build_complaint_tab()
        self._refresh_settings_status()
        self._refresh_ai_status()

    # ---------- Common settings ----------
    def _refresh_settings(self):
        self.settings = load_settings()

    def _show_error(self, title: str, message: str, *, log_message: str | None = None) -> None:
        if log_message:
            LOGGER.error(log_message)
        QMessageBox.critical(self, title, message)

    def _invalidate_openai_client(self) -> None:
        self._openai_client = None
        self._openai_client_signature = None

    def _get_openai_key(self) -> str:
        self._refresh_settings()
        return str(self.settings.get("OPENAI_API_KEY", "")).strip()

    def _get_proxy_url(self) -> str:
        self._refresh_settings()
        return str(self.settings.get("OPENAI_PROXY_URL", "")).strip() or os.getenv("OPENAI_PROXY_URL", "").strip()

    def _refresh_settings_status(self):
        active_key = self._get_openai_key()
        proxy_url = self._get_proxy_url()
        proxy_status = mask_secret(proxy_url)
        self.settings_status.setText(
            f"OpenAI key: {mask_secret(active_key)}\n"
            f"Прокси: {proxy_status}\n"
            f"Файл настроек: {SETTINGS_PATH}\n"
            f"Лог ошибок: {LOG_PATH}"
        )

        self.s_openai_key.setText(active_key)
        self.s_proxy_url.setText(str(self.settings.get("OPENAI_PROXY_URL", "")).strip())

    def _collect_urls_to_validate(self) -> List[Tuple[str, str]]:
        items = [
            ("Профиль: скан паспорта представителя", self.p_scan.text().strip()),
            ("Потерпевший: скан паспорта", self.v_scan.text().strip()),
            ("Доказательство: договор", self.ev_contract.text().strip()),
            ("Доказательство: адвокатский запрос", self.ev_bar.text().strip()),
            ("Доказательство: официальный ответ", self.ev_official_answer.text().strip()),
            ("Доказательство: уведомление по почте", self.ev_mail_notice.text().strip()),
            ("Доказательство: запись об аресте", self.ev_arrest_record.text().strip()),
            ("Доказательство: личное дело", self.ev_personnel_file.text().strip()),
        ]
        for index, line in enumerate(self.video_fix_fields, 1):
            items.append((f"Видеофиксация #{index}", line.text().strip()))
        for index, line in enumerate(self.provided_video_fields, 1):
            items.append((f"Предоставленная запись #{index}", line.text().strip()))
        return items

    def _validate_urls(self) -> list[str]:
        invalid = []
        for label, url in self._collect_urls_to_validate():
            if url and not is_valid_http_url(url):
                invalid.append(f"{label}: ожидается http/https URL")
        return invalid

    def _build_openai_client(self):
        api_key = self._get_openai_key()
        proxy_url = self._get_proxy_url()
        signature = (api_key, proxy_url)
        if self._openai_client is not None and self._openai_client_signature == signature:
            return self._openai_client

        try:
            import httpx  # type: ignore
            from openai import DefaultHttpxClient, OpenAI  # type: ignore
        except Exception:
            log_exception("Не найдены зависимости openai/httpx")
            raise RuntimeError("Не найдены пакеты 'openai' и/или 'httpx'.\nУстанови:\npython -m pip install openai httpx")

        if not api_key:
            raise RuntimeError("Сначала добавь OpenAI API key на вкладке «Локальные настройки».")
        if proxy_url and not is_valid_http_url(proxy_url):
            raise RuntimeError("Прокси должен быть указан в формате http://... или https://...")

        try:
            timeout = httpx.Timeout(
                OPENAI_TIMEOUT_SECONDS,
                connect=OPENAI_CONNECT_TIMEOUT_SECONDS,
                read=OPENAI_TIMEOUT_SECONDS,
                write=OPENAI_CONNECT_TIMEOUT_SECONDS,
            )
            http_client = DefaultHttpxClient(proxy=proxy_url or None, timeout=timeout, trust_env=False)
            client = OpenAI(api_key=api_key, max_retries=0, http_client=http_client)
        except Exception as exc:
            log_exception("Не удалось создать клиент OpenAI")
            raise RuntimeError(f"Не удалось создать клиент OpenAI:\n{exc}") from exc

        self._openai_client = client
        self._openai_client_signature = signature
        return client

    # ---------- Profile ----------
    def _build_profile_tab(self):
        layout = QVBoxLayout(self.tab_profile)
        form = QFormLayout()
        layout.addLayout(form)

        self.p_name = QLineEdit(self.rep.name)
        self.p_passport = QLineEdit(self.rep.passport)
        self.p_address = QLineEdit(self.rep.address)
        self.p_phone = QLineEdit(self.rep.phone)
        self.p_discord = QLineEdit(self.rep.discord)
        self.p_scan = QLineEdit(self.rep.passport_scan_url)

        self.p_discord.setPlaceholderText("например: 12hsrate  (или полный адрес: 12hsrate@sa.com)")

        form.addRow("ФИО представителя", self.p_name)
        form.addRow("Паспорт", self.p_passport)
        form.addRow("Адрес проживания", self.p_address)
        form.addRow("Телефон", self.p_phone)
        form.addRow("Discord (без @sa.com)", self.p_discord)
        form.addRow("Скан паспорта (URL)", self.p_scan)

        btns = QHBoxLayout()
        layout.addLayout(btns)

        btn_save = QPushButton("Сохранить профиль")
        btn_save.clicked.connect(self.on_save_profile)
        btns.addWidget(btn_save)

        btn_zero = QPushButton("Обнулить профиль")
        btn_zero.clicked.connect(self.on_zero_profile)
        btns.addWidget(btn_zero)

        btns.addStretch(1)

    def _build_settings_tab(self):
        layout = QVBoxLayout(self.tab_settings)

        status_group = QGroupBox("Состояние")
        status_layout = QVBoxLayout(status_group)
        self.settings_status = QLabel("")
        self.settings_status.setWordWrap(True)
        status_layout.addWidget(self.settings_status)
        layout.addWidget(status_group)

        form_group = QGroupBox("OpenAI")
        form_layout = QVBoxLayout(form_group)
        form = QFormLayout()
        form_layout.addLayout(form)

        self.s_openai_key = QLineEdit()
        self.s_openai_key.setPlaceholderText("sk-...")
        self.s_openai_key.setEchoMode(QLineEdit.Password)
        form.addRow("OpenAI API key", self.s_openai_key)

        self.s_proxy_url = QLineEdit()
        self.s_proxy_url.setPlaceholderText("http://user:pass@host:port")
        form.addRow("Прокси URL", self.s_proxy_url)

        self.s_show_key = QCheckBox("Показать ключ")
        self.s_show_key.toggled.connect(self.on_toggle_key_visibility)
        form_layout.addWidget(self.s_show_key)

        info = QLabel(
            "Секреты сохраняются только в профиле пользователя (%APPDATA%), а не рядом с .exe.\n"
            "Прокси можно хранить локально или передать через переменную окружения OPENAI_PROXY_URL.\n"
            f"Путь к настройкам: {SETTINGS_PATH}\n"
            f"Путь к логу: {LOG_PATH}"
        )
        info.setWordWrap(True)
        form_layout.addWidget(info)

        settings_btns = QHBoxLayout()

        btn_save_settings = QPushButton("Сохранить настройки")
        btn_save_settings.clicked.connect(self.on_save_local_settings)
        settings_btns.addWidget(btn_save_settings)

        btn_clear_settings = QPushButton("Удалить сохранённый ключ")
        btn_clear_settings.clicked.connect(self.on_clear_local_settings)
        settings_btns.addWidget(btn_clear_settings)

        btn_test_settings = QPushButton("Проверить OpenAI")
        btn_test_settings.clicked.connect(self.on_test_openai_settings)
        settings_btns.addWidget(btn_test_settings)

        btn_create_settings = QPushButton("Создать файл настроек")
        btn_create_settings.clicked.connect(self.on_create_settings_template)
        settings_btns.addWidget(btn_create_settings)

        btn_open_folder = QPushButton("Открыть папку")
        btn_open_folder.clicked.connect(self.on_open_settings_folder)
        settings_btns.addWidget(btn_open_folder)

        settings_btns.addStretch(1)
        form_layout.addLayout(settings_btns)
        layout.addWidget(form_group)
        layout.addStretch(1)

    def on_toggle_key_visibility(self, checked: bool):
        self.s_openai_key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def on_save_profile(self):
        try:
            rep = self._collect_rep()
            save_profile(rep)
            QMessageBox.information(self, "Готово", "Профиль сохранён.")
        except Exception as exc:
            log_exception("Не удалось сохранить профиль")
            self._show_error("Ошибка", f"Не удалось сохранить профиль:\n{exc}")

    def on_zero_profile(self):
        if QMessageBox.question(self, "Подтверждение", "Обнулить профиль (очистить все поля)?") != QMessageBox.Yes:
            return
        try:
            rep = Representative()
            save_profile(rep)
            self.rep = rep
            self.p_name.setText("")
            self.p_passport.setText("")
            self.p_address.setText("")
            self.p_phone.setText("")
            self.p_discord.setText("")
            self.p_scan.setText("")
            QMessageBox.information(self, "Готово", "Профиль обнулён.")
        except Exception as exc:
            log_exception("Не удалось обнулить профиль")
            self._show_error("Ошибка", f"Не удалось обнулить профиль:\n{exc}")

    def on_save_local_settings(self):
        proxy_url = self.s_proxy_url.text().strip()
        if proxy_url and not is_valid_http_url(proxy_url):
            QMessageBox.warning(self, "Неверный прокси", "Прокси должен быть указан как http://... или https://...")
            return
        try:
            data = load_settings()
            data["OPENAI_API_KEY"] = self.s_openai_key.text().strip()
            data["OPENAI_PROXY_URL"] = proxy_url
            save_settings(data)
            self._invalidate_openai_client()
            self._refresh_settings_status()
            QMessageBox.information(self, "Готово", "Локальные настройки сохранены.")
        except Exception as exc:
            log_exception("Не удалось сохранить локальные настройки")
            self._show_error("Ошибка", f"Не удалось сохранить локальные настройки:\n{exc}")

    def on_clear_local_settings(self):
        if QMessageBox.question(
            self,
            "Подтверждение",
            "Удалить сохранённые OpenAI key и прокси из локального файла?",
        ) != QMessageBox.Yes:
            return

        try:
            save_settings({"OPENAI_API_KEY": "", "OPENAI_PROXY_URL": ""})
            self._invalidate_openai_client()
            self._refresh_settings_status()
            QMessageBox.information(self, "Готово", "Сохранённые секреты удалены.")
        except Exception as exc:
            log_exception("Не удалось очистить локальные настройки")
            self._show_error("Ошибка", f"Не удалось очистить настройки:\n{exc}")

    def on_create_settings_template(self):
        try:
            write_settings_template()
            QMessageBox.information(self, "Готово", f"Файл настроек создан:\n{SETTINGS_PATH}")
        except Exception as exc:
            log_exception("Не удалось создать файл настроек")
            self._show_error("Ошибка", f"Не удалось создать файл настроек:\n{exc}")

    def on_open_settings_folder(self):
        try:
            webbrowser.open(APP_DIR.as_uri())
        except Exception:
            log_exception("Не удалось открыть папку настроек")
            QMessageBox.information(self, "Папка", str(APP_DIR))

    def on_test_openai_settings(self):
        try:
            client = self._build_openai_client()
            response = client.responses.create(model=OPENAI_MODEL, input="Reply with exactly: OK")
            output = (response.output_text or "").strip()
            if not output:
                raise RuntimeError("Модель вернула пустой ответ.")
            QMessageBox.information(self, "Готово", f"Подключение работает.\nОтвет модели: {output}")
        except Exception as exc:
            log_exception("Проверка OpenAI завершилась ошибкой")
            self._show_error(
                "Ошибка OpenAI",
                f"Не удалось проверить настройки OpenAI.\nПодробности записаны в лог:\n{LOG_PATH}\n\n{exc}",
            )

    # ---------- Complaint ----------
    def _build_complaint_tab(self):
        outer = QVBoxLayout(self.tab_complaint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        form = QFormLayout()
        layout.addLayout(form)

        self.c_no = QLineEdit()
        self.c_org = QLineEdit()
        self.c_subject = QLineEdit()
        form.addRow("Номер обращения", self.c_no)
        form.addRow("Организация объекта (LSPD/LSSD/FIB/...)", self.c_org)
        form.addRow("Объект заявления (ФИО, можно через запятую)", self.c_subject)

        form.addRow(QLabel("— Потерпевший —"), QLabel(""))
        self.v_name = QLineEdit()
        self.v_passport = QLineEdit()
        self.v_address = QLineEdit("-")
        self.v_phone = QLineEdit()
        self.v_discord = QLineEdit()
        self.v_scan = QLineEdit()
        self.v_discord.setPlaceholderText("например: kicyau  (или полный адрес: kicyau@sa.com)")

        form.addRow("ФИО", self.v_name)
        form.addRow("Паспорт", self.v_passport)
        form.addRow("Адрес", self.v_address)
        form.addRow("Телефон", self.v_phone)
        form.addRow("Discord (без @sa.com)", self.v_discord)
        form.addRow("Скан паспорта (URL)", self.v_scan)

        self.c_event_dt = QDateTimeEdit()
        self.c_event_dt.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.c_event_dt.setCalendarPopup(True)
        self.c_event_dt.setDateTime(QDateTime.currentDateTime())

        event_dt_box = QHBoxLayout()
        event_dt_box.addWidget(self.c_event_dt)

        btn_now = QPushButton("Сейчас")
        btn_now.clicked.connect(lambda: self.c_event_dt.setDateTime(QDateTime.currentDateTime()))
        event_dt_box.addWidget(btn_now)
        event_dt_box.addStretch(1)

        event_dt_host = QWidget()
        event_dt_host.setLayout(event_dt_box)
        form.addRow("Дата/время событий", event_dt_host)

        self.desc_placeholder = QCheckBox("Заполнить позже (оставить %%SITUATION_DESCRIPTION%%)")
        self.violation_placeholder = QCheckBox("Заполнить позже (оставить %%VIOLATION_SHORT%%)")

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText("Черновик описания событий (что произошло)…")

        self.violation_line = QLineEdit()
        self.violation_line.setPlaceholderText("Краткая формулировка нарушения (1 строка)")

        form.addRow(self.desc_placeholder, QLabel(""))
        form.addRow("Пункт 3 (описание)", self.txt_desc)

        ai_group = QGroupBox("AI-проверка пункта 3 (1 нейтральный вариант под ОГП)")
        ai_layout = QVBoxLayout(ai_group)

        self.ai_status = QLabel("Осталось AI-попыток для этой жалобы: 2")
        self.ai_status.setWordWrap(True)
        ai_layout.addWidget(self.ai_status)

        ai_note = QLabel(
            "AI не будет сам добавлять статьи и нормы, если их нет в твоём черновике.\n"
            f"На одну жалобу доступно {AI_ATTEMPTS_LIMIT} попытки. Сброс - кнопкой «Новая жалоба».\n"
            "Ключ и прокси берутся из вкладки «Локальные настройки»."
        )
        ai_note.setWordWrap(True)
        ai_layout.addWidget(ai_note)

        ai_btns = QHBoxLayout()
        self.ai_btn = QPushButton("Предложить нейтральный вариант")
        self.ai_btn.clicked.connect(self.on_ai_suggest_desc)
        ai_btns.addWidget(self.ai_btn)

        self.ai_apply = QPushButton("Применить вариант в пункт 3")
        self.ai_apply.clicked.connect(self.on_ai_apply_desc)
        ai_btns.addWidget(self.ai_apply)
        ai_btns.addStretch(1)
        ai_layout.addLayout(ai_btns)

        self.ai_out = QTextEdit()
        self.ai_out.setPlaceholderText("Здесь появится предложенный AI-вариант...")
        ai_layout.addWidget(self.ai_out)

        layout.addWidget(ai_group)

        form.addRow(self.violation_placeholder, QLabel(""))
        form.addRow("Пункт 4 (нарушение)", self.violation_line)

        form.addRow(QLabel("- Доказательства (пункт 6) -"), QLabel(""))

        self.ev_contract = QLineEdit()
        self.ev_bar = QLineEdit()
        self.ev_official_answer = QLineEdit()
        self.ev_mail_notice = QLineEdit()
        self.ev_arrest_record = QLineEdit()
        self.ev_personnel_file = QLineEdit()

        form.addRow("Договор на оказание юридических услуг (URL) *", self.ev_contract)
        form.addRow("Адвокатский запрос (URL)", self.ev_bar)
        form.addRow("Официальный ответ на адвокатский запрос (URL)", self.ev_official_answer)
        form.addRow("Уведомление посредством почты (URL)", self.ev_mail_notice)
        form.addRow("Запись об аресте (URL)", self.ev_arrest_record)

        self.video_fix_fields: List[QLineEdit] = []
        self.video_fix_container = QVBoxLayout()
        self._add_video_fix_field()

        video_fix_wrap = QWidget()
        video_fix_wrap.setLayout(self.video_fix_container)

        video_fix_box = QVBoxLayout()
        video_fix_box.addWidget(video_fix_wrap)
        add_fix_btn = QPushButton("Добавить ещё поле")
        add_fix_btn.clicked.connect(self._add_video_fix_field)
        video_fix_box.addWidget(add_fix_btn)

        video_fix_host = QWidget()
        video_fix_host.setLayout(video_fix_box)
        form.addRow("Видеофиксация процессуальных действий", video_fix_host)

        self.provided_video_fields: List[QLineEdit] = []
        self.provided_video_container = QVBoxLayout()
        self._add_provided_video_field()

        provided_wrap = QWidget()
        provided_wrap.setLayout(self.provided_video_container)

        provided_box = QVBoxLayout()
        provided_box.addWidget(provided_wrap)
        add_prov_btn = QPushButton("Добавить ещё поле")
        add_prov_btn.clicked.connect(self._add_provided_video_field)
        provided_box.addWidget(add_prov_btn)

        provided_host = QWidget()
        provided_host.setLayout(provided_box)
        form.addRow("Предоставленная запись процессуальных действий", provided_host)

        form.addRow("Личное дело (URL)", self.ev_personnel_file)

        note = QLabel(
            "Заполняй только те доказательства, которые реально есть или требуются.\n"
            "Пустые поля автоматически не попадут в пункт 6."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        btns = QHBoxLayout()
        layout.addLayout(btns)

        btn_new = QPushButton("Новая жалоба")
        btn_new.clicked.connect(self.on_new_complaint)
        btns.addWidget(btn_new)

        btn_gen = QPushButton("Сгенерировать BBCode")
        btn_gen.clicked.connect(self.on_generate)
        btns.addWidget(btn_gen)

        btn_copy = QPushButton("Копировать")
        btn_copy.clicked.connect(self.on_copy)
        btns.addWidget(btn_copy)

        btn_save = QPushButton("Сохранить в файл...")
        btn_save.clicked.connect(self.on_save)
        btns.addWidget(btn_save)

        btns.addStretch(1)

        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 10))
        layout.addWidget(self.out)

    def _make_url_field(self, placeholder: str = "URL"):
        line = QLineEdit()
        line.setPlaceholderText(placeholder)
        return line

    def _add_video_fix_field(self):
        line = self._make_url_field("URL видеофиксации")
        self.video_fix_fields.append(line)
        self.video_fix_container.addWidget(line)

    def _add_provided_video_field(self):
        line = self._make_url_field("URL предоставленной записи")
        self.provided_video_fields.append(line)
        self.provided_video_container.addWidget(line)

    def _refresh_ai_status(self):
        left = max(0, AI_ATTEMPTS_LIMIT - self.ai_attempts_used)
        self.ai_status.setText(f"Осталось AI-попыток для этой жалобы: {left}")
        self.ai_btn.setEnabled(left > 0)

    def _event_dt_text(self) -> str:
        return self.c_event_dt.dateTime().toString("dd.MM.yyyy HH:mm")

    def _today_text(self) -> str:
        return QDateTime.currentDateTime().toString("dd.MM.yyyy")

    def on_new_complaint(self):
        if QMessageBox.question(self, "Подтверждение", "Очистить текущую жалобу и начать новую?") != QMessageBox.Yes:
            return

        self.c_no.clear()
        self.c_org.clear()
        self.c_subject.clear()

        self.v_name.clear()
        self.v_passport.clear()
        self.v_address.setText("-")
        self.v_phone.clear()
        self.v_discord.clear()
        self.v_scan.clear()

        self.c_event_dt.setDateTime(QDateTime.currentDateTime())
        self.desc_placeholder.setChecked(False)
        self.violation_placeholder.setChecked(False)
        self.txt_desc.clear()
        self.violation_line.clear()

        self.ev_contract.clear()
        self.ev_bar.clear()
        self.ev_official_answer.clear()
        self.ev_mail_notice.clear()
        self.ev_arrest_record.clear()
        self.ev_personnel_file.clear()

        for line in self.video_fix_fields:
            line.setParent(None)
            line.deleteLater()
        self.video_fix_fields.clear()
        self._add_video_fix_field()

        for line in self.provided_video_fields:
            line.setParent(None)
            line.deleteLater()
        self.provided_video_fields.clear()
        self._add_provided_video_field()

        self.ai_out.clear()
        self.out.clear()
        self.ai_attempts_used = 0
        self._refresh_ai_status()

        QMessageBox.information(self, "Готово", "Форма очищена. Можно заполнять новую жалобу.")

    def _validate(self) -> bool:
        errors = shared_validate_complaint_input(self._build_shared_complaint_input())
        if errors:
            QMessageBox.critical(self, "Не заполнено", "Исправь поля:\n• " + "\n• ".join(errors))
            return False
        return True

    def _collect_rep(self) -> Representative:
        rep = Representative(
            name=self.p_name.text().strip(),
            passport=self.p_passport.text().strip(),
            address=self.p_address.text().strip(),
            phone=self.p_phone.text().strip(),
            discord=self.p_discord.text().strip(),
            passport_scan_url=self.p_scan.text().strip(),
        )
        save_profile(rep)
        self.rep = rep
        return rep

    def _collect_victim(self) -> Victim:
        return Victim(
            name=self.v_name.text().strip(),
            passport=self.v_passport.text().strip(),
            address=self.v_address.text().strip() or "-",
            phone=self.v_phone.text().strip(),
            discord=self.v_discord.text().strip(),
            passport_scan_url=self.v_scan.text().strip(),
        )

    def _collect_evidence(self) -> List[Tuple[str, str]]:
        mapping: List[Tuple[str, str]] = [
            ("Договор на оказание юридических услуг", self.ev_contract.text().strip()),
            ("Адвокатский запрос", self.ev_bar.text().strip()),
            ("Официальный ответ на адвокатский запрос", self.ev_official_answer.text().strip()),
            ("Уведомление посредством почты", self.ev_mail_notice.text().strip()),
            ("Запись об аресте", self.ev_arrest_record.text().strip()),
            ("Личное дело", self.ev_personnel_file.text().strip()),
        ]

        for line in self.video_fix_fields:
            url = line.text().strip()
            if url:
                mapping.append(("Видеофиксация процессуальных действий", url))

        for line in self.provided_video_fields:
            url = line.text().strip()
            if url:
                mapping.append(("Предоставленная запись процессуальных действий", url))

        return [(title, url) for title, url in mapping if url]

    def _build_shared_complaint_input(self) -> SharedComplaintInput:
        rep = self._collect_rep()
        victim = self._collect_victim()

        desc = DEFAULT_SITUATION_PLACEHOLDER if self.desc_placeholder.isChecked() else self.txt_desc.toPlainText().strip()
        if not desc:
            desc = DEFAULT_SITUATION_PLACEHOLDER

        viol = DEFAULT_VIOLATION_PLACEHOLDER if self.violation_placeholder.isChecked() else self.violation_line.text().strip()
        if not viol:
            viol = DEFAULT_VIOLATION_PLACEHOLDER

        return SharedComplaintInput(
            appeal_no=self.c_no.text().strip(),
            org=self.c_org.text().strip(),
            subject_names=self.c_subject.text().strip(),
            situation_description=desc,
            violation_short=viol,
            event_dt=self._event_dt_text(),
            today_date=self._today_text(),
            representative=rep,
            victim=victim,
            evidence_items=shared_collect_evidence_items(
                contract_url=self.ev_contract.text().strip(),
                bar_request_url=self.ev_bar.text().strip(),
                official_answer_url=self.ev_official_answer.text().strip(),
                mail_notice_url=self.ev_mail_notice.text().strip(),
                arrest_record_url=self.ev_arrest_record.text().strip(),
                personnel_file_url=self.ev_personnel_file.text().strip(),
                video_fix_urls=[line.text().strip() for line in self.video_fix_fields if line.text().strip()],
                provided_video_urls=[line.text().strip() for line in self.provided_video_fields if line.text().strip()],
            ),
        )

    def on_ai_suggest_desc(self):
        if self.ai_attempts_used >= AI_ATTEMPTS_LIMIT:
            QMessageBox.warning(
                self,
                "Лимит исчерпан",
                f"Для этой жалобы уже использованы {AI_ATTEMPTS_LIMIT} AI-попытки.\nНажми «Новая жалоба», чтобы начать заново.",
            )
            return

        victim_name = self.v_name.text().strip()
        event_dt = self._event_dt_text()
        org = self.c_org.text().strip()
        subject = self.c_subject.text().strip()
        raw_desc = self.txt_desc.toPlainText().strip()

        if not victim_name or not event_dt or not org or not subject:
            QMessageBox.warning(self, "Не заполнено", "Заполни: доверитель, дата/время, организация, объект заявления.")
            return
        if not raw_desc:
            QMessageBox.warning(self, "Нет черновика", "Сначала заполни черновик описания событий (пункт 3).")
            return

        try:
            out = suggest_description_with_proxy_fallback(
                api_key=self._get_openai_key(),
                proxy_url=self._get_proxy_url(),
                victim_name=victim_name,
                org=org,
                subject=subject,
                event_dt=event_dt,
                raw_desc=raw_desc,
            )
            if not out:
                QMessageBox.warning(self, "Пустой ответ", "Модель вернула пустой ответ. Попробуй ещё раз.")
                return
            self.ai_out.setPlainText(out)
            self.ai_attempts_used += 1
            self._refresh_ai_status()
        except Exception as exc:
            log_exception("Не удалось получить ответ от OpenAI")
            self._show_error(
                "Ошибка запроса",
                "Не удалось получить ответ от модели.\n"
                f"Подробности записаны в лог:\n{LOG_PATH}\n\n"
                f"Тип ошибки: {exc.__class__.__name__}\n"
                f"Полная ошибка OpenAI:\n{exc}",
            )

    def on_ai_apply_desc(self):
        suggestion = self.ai_out.toPlainText().strip()
        if not suggestion:
            QMessageBox.warning(self, "Нет варианта", "Сначала нажми «Предложить нейтральный вариант».")
            return
        self.txt_desc.setPlainText(suggestion)

    def on_generate(self):
        if not self._validate():
            return

        try:
            complaint = self._build_shared_complaint_input()
            self.out.setPlainText(shared_build_bbcode(complaint))
        except Exception as exc:
            log_exception("Не удалось сгенерировать BBCode")
            self._show_error(
                "Ошибка генерации",
                f"Не удалось сгенерировать BBCode.\nПодробности записаны в лог:\n{LOG_PATH}\n\n{exc}",
            )

    def on_copy(self):
        txt = self.out.toPlainText().strip()
        if not txt:
            QMessageBox.warning(self, "Нет текста", "Сначала нажми «Сгенерировать BBCode».")
            return
        QApplication.clipboard().setText(txt)
        QMessageBox.information(self, "Готово", "BBCode скопирован в буфер обмена.")

    def on_save(self):
        txt = self.out.toPlainText().strip()
        if not txt:
            QMessageBox.warning(self, "Нет текста", "Сначала нажми «Сгенерировать BBCode».")
            return

        default_name = f"Обращение_{self.c_no.text().strip() or '____'}.bbcode.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить BBCode",
            str(APP_DIR / default_name),
            "Text (*.txt);;All files (*.*)",
        )
        if not path:
            return
        try:
            atomic_write_text(Path(path), txt)
            QMessageBox.information(self, "Готово", f"Сохранено:\n{path}")
        except Exception as exc:
            log_exception("Не удалось сохранить BBCode в файл")
            self._show_error(
                "Ошибка сохранения",
                f"Не удалось сохранить файл.\nПодробности записаны в лог:\n{LOG_PATH}\n\n{exc}",
            )



def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
