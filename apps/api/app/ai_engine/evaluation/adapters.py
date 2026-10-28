"""Gemini Adapters for Ragas LLM and Embeddings using the official google-genai SDK."""

from __future__ import annotations

import asyncio
import logging
import random
import typing as t

from google import genai
from google.genai import errors, types
from langchain_core.callbacks import Callbacks
from langchain_core.outputs import Generation, LLMResult
from langchain_core.prompt_values import PromptValue
from ragas.embeddings.base import BaseRagasEmbeddings
from ragas.llms.base import BaseRagasLLM

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiRagasLLM(BaseRagasLLM):
    """Native Ragas LLM wrapper using google-genai SDK for Gemini models."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        max_retries: int = 4,
        base_delay: float = 1.0,
    ) -> None:
        super().__init__()
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or configured in settings.")
        self.model_name = model_name or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.client = genai.Client(api_key=self.api_key)

    def _execute_with_retry_sync(self, func: t.Callable[[], str]) -> str:
        delay = self.base_delay
        for attempt in range(self.max_retries + 1):
            try:
                return func()
            except errors.ClientError as exc:
                if exc.code == 429 and attempt < self.max_retries:
                    jitter = random.uniform(0.5, 1.5)
                    sleep_time = delay * jitter
                    logger.warning("Gemini 429 rate limit hit. Retrying in %.2fs (attempt %d/%d)", sleep_time, attempt + 1, self.max_retries)
                    import time
                    time.sleep(sleep_time)
                    delay *= 2
                else:
                    raise

    async def _execute_with_retry_async(self, coro_func: t.Callable[[], t.Awaitable[str]]) -> str:
        delay = self.base_delay
        for attempt in range(self.max_retries + 1):
            try:
                return await coro_func()
            except errors.ClientError as exc:
                if exc.code == 429 and attempt < self.max_retries:
                    jitter = random.uniform(0.5, 1.5)
                    sleep_time = delay * jitter
                    logger.warning("Gemini 429 rate limit hit. Retrying in %.2fs (attempt %d/%d)", sleep_time, attempt + 1, self.max_retries)
                    await asyncio.sleep(sleep_time)
                    delay *= 2
                else:
                    raise

    def generate_text(
        self,
        prompt: PromptValue,
        n: int = 1,
        temperature: float = 0.01,
        stop: list[str] | None = None,
        callbacks: Callbacks = None,
    ) -> LLMResult:
        text_prompt = prompt.to_string()

        def _call() -> str:
            res = self.client.models.generate_content(
                model=self.model_name,
                contents=text_prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            return res.text or ""

        text = self._execute_with_retry_sync(_call)
        return LLMResult(generations=[[Generation(text=text)]])

    async def agenerate_text(
        self,
        prompt: PromptValue,
        n: int = 1,
        temperature: float = 0.01,
        stop: list[str] | None = None,
        callbacks: Callbacks = None,
    ) -> LLMResult:
        text_prompt = prompt.to_string()

        async def _call() -> str:
            res = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=text_prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            return res.text or ""

        text = await self._execute_with_retry_async(_call)
        return LLMResult(generations=[[Generation(text=text)]])

    def is_finished(self, response: LLMResult) -> bool:
        return True


class GeminiRagasEmbeddings(BaseRagasEmbeddings):
    """Native Ragas Embeddings wrapper using google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "models/gemini-embedding-001",
        max_retries: int = 4,
        base_delay: float = 0.5,
    ) -> None:
        super().__init__()
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or configured in settings.")
        self.model_name = model_name
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.client = genai.Client(api_key=self.api_key)

    def embed_query(self, text: str) -> list[float]:
        res = self.client.models.embed_content(model=self.model_name, contents=text)
        return list(res.embeddings[0].values)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    async def aembed_query(self, text: str) -> list[float]:
        delay = self.base_delay
        for attempt in range(self.max_retries + 1):
            try:
                res = await self.client.aio.models.embed_content(
                    model=self.model_name, contents=text
                )
                return list(res.embeddings[0].values)
            except errors.ClientError as exc:
                if exc.code == 429 and attempt < self.max_retries:
                    jitter = random.uniform(0.5, 1.5)
                    await asyncio.sleep(delay * jitter)
                    delay *= 2
                else:
                    raise

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        tasks = [self.aembed_query(t) for t in texts]
        return await asyncio.gather(*tasks)
