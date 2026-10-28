#!/usr/bin/env python3
"""CLI utility to run RAG benchmark evaluations and generate synthetic testsets."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add apps/api to sys.path so app imports work seamlessly
current_dir = Path(__file__).resolve().parent
api_root = current_dir.parent
if str(api_root) not in sys.path:
    sys.path.insert(0, str(api_root))

from app.ai_engine.evaluation.adapters import GeminiRagasEmbeddings, GeminiRagasLLM
from app.ai_engine.evaluation.dataset_generator import SyntheticDatasetGenerator
from app.ai_engine.evaluation.reporter import save_report
from app.ai_engine.evaluation.runner import RAGEvaluationRunner
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_rag")


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="AI Learning Platform - RAG Evaluation CLI")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=api_root / "data" / "evaluation" / "golden_dataset.json",
        help="Path to the JSON evaluation dataset.",
    )
    parser.add_argument(
        "--generate-dataset",
        action="store_true",
        help="Generate a synthetic dataset from documents instead of running evaluation.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=api_root / "data" / "evaluation" / "sample_docs",
        help="Directory containing markdown/text documents to synthesize questions from.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=api_root / "data" / "evaluation" / "synthetic_dataset.json",
        help="Target output path for generated synthetic dataset.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=api_root / "data" / "evaluation" / "reports",
        help="Directory where Markdown/JSON reports are saved.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=settings.GEMINI_MODEL or "gemini-3.5-flash-lite",
        help="Gemini model to use as LLM Judge.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="RAG Quality Benchmark",
        help="Report title.",
    )

    args = parser.parse_args()

    # Mode 1: Synthetic Dataset Generation
    if args.generate_dataset:
        logger.info("Starting Synthetic Dataset Generation from: %s", args.docs_dir)
        generator = SyntheticDatasetGenerator(model_name=args.model)
        samples = await generator.generate_from_directory(
            docs_dir=args.docs_dir,
            output_file=args.output_file,
        )
        print(f"\n✅ Successfully generated {len(samples)} evaluation samples -> {args.output_file}")
        return 0

    # Mode 2: Benchmark Evaluation
    if not args.dataset.exists():
        logger.error("Evaluation dataset not found at %s", args.dataset)
        return 1

    logger.info("Loading evaluation dataset from: %s", args.dataset)
    with open(args.dataset, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        logger.error("Dataset must be a non-empty JSON list.")
        return 1

    llm = GeminiRagasLLM(model_name=args.model)
    embeddings = GeminiRagasEmbeddings()
    runner = RAGEvaluationRunner(llm=llm, embeddings=embeddings)

    print(f"\n🚀 Running RAG Evaluation ({len(data)} samples) with Judge: {args.model}...\n")
    report = await runner.run(dataset=data, title=args.title)

    md_path, json_path = save_report(report, output_dir=args.reports_dir)

    print("=" * 60)
    print(f"📊 EVALUATION REPORT: {report.title}")
    print("=" * 60)
    print(f"Total Samples : {report.sample_count}")
    print(f"Judge Model   : {report.model_name}")
    print(f"Status        : {'PASSED (Quality Gate Met)' if report.passed else 'FAILED (Below Threshold)'}")
    print("-" * 60)
    for m_name, score in report.average_scores.items():
        thresh = report.thresholds.get(m_name, 0.0)
        mark = "✓ PASS" if score >= thresh else "✗ FAIL"
        print(f"{m_name:<20}: {score:.4f} (Threshold: {thresh:.2f}) [{mark}]")
    print("=" * 60)
    print(f"📄 Markdown Report : {md_path}")
    print(f"💾 JSON Summary    : {json_path}")
    print("=" * 60 + "\n")

    return 0 if report.passed else 1


def main() -> None:
    code = asyncio.run(main_async())
    sys.exit(code)


if __name__ == "__main__":
    main()
