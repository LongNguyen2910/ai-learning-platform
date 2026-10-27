"""Gemini streaming client cho Chat Tutor."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from google import genai
from google.genai import types

from app.core.config import settings


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "model"]
    text: str


class ChatLLMClient(Protocol):
    def stream(
        self, system_prompt: str, history: Sequence[ChatTurn], user_message: str
    ) -> AsyncIterator[str]: ...


class GeminiChatClient:
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.4,
        max_output_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not configured in settings or environment."
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def stream(
        self, system_prompt: str, history: Sequence[ChatTurn], user_message: str
    ) -> AsyncIterator[str]:
        contents = [
            types.Content(role=turn.role, parts=[types.Part.from_text(text=turn.text)])
            for turn in history
            if turn.text
        ]
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )
        response_stream = await self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=contents,
            config=config,
        )
        async for chunk in response_stream:
            text = chunk.text
            if text:
                yield text


gemini_chat_client = GeminiChatClient()
