"use client";

import { FormEvent, useState } from "react";
import { login } from "../lib/api";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await login({ email, password });
      localStorage.setItem("auth_token", result.token);
      setSuccess("Вход выполнен. Токен сохранен в localStorage.");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Ошибка входа");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit}>
      <h1 style={{ marginTop: 0 }}>Вход в систему</h1>
      <p className="helper">Используйте email и пароль учетной записи.</p>

      <label>
        Email
        <input
          className="input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          required
        />
      </label>

      <div style={{ height: 12 }} />

      <label>
        Пароль
        <input
          className="input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="********"
          required
          minLength={8}
        />
      </label>

      <div style={{ height: 16 }} />

      <button className="button" type="submit" disabled={loading}>
        {loading ? "Входим..." : "Войти"}
      </button>

      {error ? <p className="helper error">{error}</p> : null}
      {success ? <p className="helper success">{success}</p> : null}
    </form>
  );
}
