from __future__ import annotations

from dataclasses import dataclass

from shared.ogp_ai import create_openai_client

from .interfaces import RetryPolicy


@dataclass(frozen=True)
class OpenAITransport:
    api_key: str
    proxy_url: str

    def build_client(self):
        return create_openai_client(api_key=self.api_key, proxy_url=self.proxy_url)


def default_retry_policy(*, max_attempts: int = 5) -> RetryPolicy:
    return RetryPolicy(max_attempts=max(1, int(max_attempts or 1)))
