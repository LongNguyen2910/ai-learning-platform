"""Synthetic Testset Generator using Gemini for learning materials."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)


class SyntheticDatasetGenerator:
    """Generates synthetic (Q, A, Context) testsets from documents using Gemini."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required.")
        self.model_name = model_name or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.client = genai.Client(api_key=self.api_key)

    async def generate_from_text(
        self,
        text_content: str,
        num_questions: int = 5,
    ) -> list[dict[str, Any]]:
        """Generates evaluation Q&A pairs from a text document."""
        prompt = f"""You are an expert educational content evaluator. Given the following educational text, generate exactly {num_questions} high-quality question-and-answer pairs for evaluation.

Requirements for each item:
1. 'user_input': A natural student query or test question testing comprehension or application of a specific concept in the text.
2. 'reference': The definitive, complete ground-truth answer based purely on the provided text.
3. 'retrieved_contexts': A list containing the specific paragraph or excerpt from the text that provides evidence for the answer.

Text Content:
\"\"\"
{text_content[:8000]}
\"\"\"

Output strictly a JSON list of objects with keys: "user_input", "reference", "retrieved_contexts". Do not include markdown code block syntax.
"""
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        try:
            raw_text = response.text or "[]"
            # Strip potential ```json wrappers if any
            if raw_text.startswith("```"):
                lines = raw_text.strip().split("\n")
                raw_text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
            data = json.loads(raw_text)
            if isinstance(data, list):
                return data
            return []
        except Exception as exc:
            logger.error("Failed to parse synthetic dataset JSON: %s", exc)
            return []

    async def generate_from_directory(
        self,
        docs_dir: Path,
        output_file: Path,
        questions_per_file: int = 3,
    ) -> list[dict[str, Any]]:
        """Scans docs_dir for markdown/text files and writes a combined synthetic dataset."""
        all_samples: list[dict[str, Any]] = []
        files = list(docs_dir.glob("**/*.md")) + list(docs_dir.glob("**/*.txt"))

        for file_path in files:
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                continue
            logger.info("Generating questions from: %s", file_path.name)
            samples = await self.generate_from_text(content, num_questions=questions_per_file)
            all_samples.extend(samples)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(all_samples, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved %d synthetic evaluation samples to %s", len(all_samples), output_file)
        return all_samples
