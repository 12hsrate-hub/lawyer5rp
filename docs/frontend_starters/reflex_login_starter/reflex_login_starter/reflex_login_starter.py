import httpx
import reflex as rx


API_BASE_URL = "http://localhost:8000"


class LoginState(rx.State):
    email: str = ""
    password: str = ""
    loading: bool = False
    error: str = ""
    success: str = ""

    async def submit(self):
        self.loading = True
        self.error = ""
        self.success = ""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{API_BASE_URL}/auth/login",
                    json={"email": self.email, "password": self.password},
                )

            if response.status_code >= 400:
                self.error = response.text or "Не удалось выполнить вход"
                return

            data = response.json()
            token = data.get("token", "")
            self.success = f"Вход выполнен. Токен: {token[:12]}..."
        except Exception as err:  # noqa: BLE001
            self.error = str(err)
        finally:
            self.loading = False


def login_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.heading("Вход в систему", size="6"),
            rx.text("Минимальный шаблон логина на Reflex."),
            rx.input(
                placeholder="you@example.com",
                value=LoginState.email,
                on_change=LoginState.set_email,
                type="email",
            ),
            rx.input(
                placeholder="********",
                value=LoginState.password,
                on_change=LoginState.set_password,
                type="password",
            ),
            rx.button(
                rx.cond(LoginState.loading, "Входим...", "Войти"),
                on_click=LoginState.submit,
                loading=LoginState.loading,
                width="100%",
            ),
            rx.cond(LoginState.error != "", rx.text(LoginState.error, color="red")),
            rx.cond(LoginState.success != "", rx.text(LoginState.success, color="green")),
            spacing="3",
            width="100%",
        ),
        width="100%",
        max_width="420px",
    )


def index() -> rx.Component:
    return rx.center(
        login_card(),
        min_height="100vh",
        padding="24px",
    )


app = rx.App()
app.add_page(index, route="/")
