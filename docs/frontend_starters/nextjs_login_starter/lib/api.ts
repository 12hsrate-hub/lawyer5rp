export type LoginPayload = {
  email: string;
  password: string;
};

export async function login(payload: LoginPayload): Promise<{ token: string }> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

  const response = await fetch(`${baseUrl}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Не удалось выполнить вход");
  }

  return response.json();
}
