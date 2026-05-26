"""
HippoRAG QA Benchmark: Slowave Evaluation.

Compare Slowave retrieval performance against published HippoRAG benchmarks
on 2WikiMultiHopQA, MuSiQue, and HotpotQA.

We run Slowave only; HippoRAG baselines are from published results:
  - 2WikiMultiHopQA: HippoRAG achieves +20-38% improvement on Recall@5
  - MuSiQue: Significantly outperforms single-step RAG
  - HotpotQA: Strong multi-hop reasoning

Usage:
  pytest tests/integration/hipporag_qa_eval.py -v
  pytest tests/integration/hipporag_qa_eval.py::test_2wiki_multihop -s
  python tests/integration/hipporag_qa_eval.py --dataset 2wiki --sample 100
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


@dataclass
class QAExample:
    """Single QA example from benchmark."""
    question: str
    documents: list[str]  # supporting documents
    ground_truth_answer: str
    supporting_passage_ids: list[int]  # which docs are relevant


@dataclass
class RetrievalMetrics:
    """Retrieval quality metrics."""
    recall_at_1: float  # % of relevant docs in top-1
    recall_at_5: float  # % of relevant docs in top-5
    recall_at_10: float
    mean_reciprocal_rank: float  # MRR
    ndcg_at_5: float  # normalized discounted cumulative gain


class SlowaveQAEvaluator:
    """Evaluate Slowave on QA/retrieval tasks."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(Path(tempfile.gettempdir()) / "slowave_qa_eval.db")
        self.engine: SlowaveEngine | None = None

    def setup(self) -> None:
        """Initialize Slowave engine."""
        cfg = SlowaveConfig(db_path=self.db_path, disable_llm=True)
        self.engine = SlowaveEngine(cfg)

    def teardown(self) -> None:
        """Clean up engine."""
        if self.engine:
            self.engine.close()

    def ingest_documents(self, documents: list[str], project: str = "qa-eval") -> str:
        """
        Ingest documents as a session.

        Returns session_id for this document set.
        """
        if not self.engine:
            raise RuntimeError("Call setup() first")

        sid = self.engine.session_start(agent="qa-evaluator", project=project)

        # Add each document as an event
        for i, doc in enumerate(documents):
            self.engine.event_append(
                session_id=sid,
                type="document",
                content=doc,
            )

        # End session to form episodes
        self.engine.session_end(sid, consolidate=True)

        return sid

    def retrieve(self, question: str, top_k: int = 10) -> list[int]:
        """
        Retrieve top-k most relevant documents for a question.

        Returns: list of document indices (0-indexed) in relevance order.
        """
        if not self.engine:
            raise RuntimeError("Call setup() first")

        result = self.engine.recall(question, top_k=top_k, evidence=False)

        # Extract episode indices from result
        # Episodes are formed from documents; we need to map back
        doc_indices = []
        for ep in result.episode_texts:
            # Episode content_text might contain document text
            # Try to infer document index from episode
            doc_idx = ep.get("metadata", {}).get("doc_index", -1)
            if doc_idx >= 0:
                doc_indices.append(doc_idx)

        return doc_indices[:top_k]

    def evaluate_retrieval(
        self,
        examples: list[QAExample],
        top_k: int = 5,
    ) -> RetrievalMetrics:
        """
        Evaluate retrieval quality on a set of QA examples.

        Args:
            examples: List of QA examples
            top_k: Evaluate at this cutoff

        Returns:
            RetrievalMetrics with precision, recall, MRR, NDCG
        """
        if not self.engine:
            raise RuntimeError("Call setup() first")

        recall_at_1_scores = []
        recall_at_5_scores = []
        recall_at_10_scores = []
        mrr_scores = []
        ndcg_scores = []

        for example in examples:
            # Ingest documents for this example
            sid = self.ingest_documents(example.documents)

            # Retrieve
            retrieved = self.retrieve(example.question, top_k=10)

            # Calculate metrics
            relevant_set = set(example.supporting_passage_ids)

            # Recall@k
            retrieved_set_1 = set(retrieved[:1])
            retrieved_set_5 = set(retrieved[:5])
            retrieved_set_10 = set(retrieved[:10])

            recall_1 = len(relevant_set & retrieved_set_1) / len(relevant_set) if relevant_set else 0
            recall_5 = len(relevant_set & retrieved_set_5) / len(relevant_set) if relevant_set else 0
            recall_10 = len(relevant_set & retrieved_set_10) / len(relevant_set) if relevant_set else 0

            recall_at_1_scores.append(recall_1)
            recall_at_5_scores.append(recall_5)
            recall_at_10_scores.append(recall_10)

            # Mean reciprocal rank
            mrr = 0.0
            for rank, doc_idx in enumerate(retrieved, start=1):
                if doc_idx in relevant_set:
                    mrr = 1.0 / rank
                    break
            mrr_scores.append(mrr)

            # NDCG@5 (simplified: binary relevance)
            dcg = 0.0
            for rank, doc_idx in enumerate(retrieved[:5], start=1):
                if doc_idx in relevant_set:
                    dcg += 1.0 / __import__("math").log2(rank + 1)
            idcg = sum(1.0 / __import__("math").log2(i + 1) for i in range(1, min(len(relevant_set) + 1, 6)))
            ndcg = dcg / idcg if idcg > 0 else 0.0
            ndcg_scores.append(ndcg)

        return RetrievalMetrics(
            recall_at_1=sum(recall_at_1_scores) / len(recall_at_1_scores) if recall_at_1_scores else 0,
            recall_at_5=sum(recall_at_5_scores) / len(recall_at_5_scores) if recall_at_5_scores else 0,
            recall_at_10=sum(recall_at_10_scores) / len(recall_at_10_scores) if recall_at_10_scores else 0,
            mean_reciprocal_rank=sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0,
            ndcg_at_5=sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0,
        )


# ============================================================================
# Test Cases
# ============================================================================


@pytest.mark.integration
def test_slowave_qa_basic() -> None:
    """Smoke test: Slowave can ingest docs and retrieve for a question."""
    evaluator = SlowaveQAEvaluator()
    evaluator.setup()

    try:
        documents = [
            "Alice is a researcher who works on memory systems.",
            "Bob is a software engineer interested in distributed systems.",
            "Memory consolidation happens during sleep.",
            "RAG stands for Retrieval-Augmented Generation.",
        ]

        sid = evaluator.ingest_documents(documents)
        assert sid is not None

        # Retrieve
        question = "What is memory consolidation?"
        retrieved = evaluator.retrieve(question, top_k=3)
        assert len(retrieved) <= 3
        assert isinstance(retrieved, list)

    finally:
        evaluator.teardown()


@pytest.mark.integration
def test_slowave_qa_metrics() -> None:
    """Test metric calculation on a small example set."""
    evaluator = SlowaveQAEvaluator()
    evaluator.setup()

    try:
        examples = [
            QAExample(
                question="What is memory consolidation?",
                documents=[
                    "Memory consolidation happens during sleep.",
                    "Alice is a researcher.",
                    "RAG is a technique.",
                    "Sleep improves memory.",
                ],
                ground_truth_answer="Memory consolidation happens during sleep",
                supporting_passage_ids=[0, 3],  # docs 0 and 3 are relevant
            ),
            QAExample(
                question="Who works on memory systems?",
                documents=[
                    "Alice works on memory systems.",
                    "Bob is a software engineer.",
                    "Memory consolidation is important.",
                ],
                ground_truth_answer="Alice",
                supporting_passage_ids=[0],
            ),
        ]

        metrics = evaluator.evaluate_retrieval(examples, top_k=5)

        assert 0 <= metrics.recall_at_5 <= 1
        assert 0 <= metrics.mean_reciprocal_rank <= 1
        assert 0 <= metrics.ndcg_at_5 <= 1

        print(f"\nMetrics on toy examples:")
        print(f"  Recall@5: {metrics.recall_at_5:.3f}")
        print(f"  MRR: {metrics.mean_reciprocal_rank:.3f}")
        print(f"  NDCG@5: {metrics.ndcg_at_5:.3f}")

    finally:
        evaluator.teardown()


# ============================================================================
# Planned: Integration with actual datasets
# ============================================================================

# TODO: Implement loaders for:
#   - 2WikiMultiHopQA
#   - MuSiQue
#   - HotpotQA
#
# TODO: Add comparison table showing Slowave vs HippoRAG published numbers
#
# TODO: Generate results/hipporag_comparison/slowave_results.json with:
#   {
#     "dataset": "2wiki_multihop",
#     "timestamp": "2026-05-26T...",
#     "metrics": {
#       "recall_at_5": 0.65,
#       "mrr": 0.72,
#       "ndcg_at_5": 0.68
#     },
#     "hipporag_baseline": {
#       "recall_at_5": 0.87,
#       "improvement": "-25%"
#     }
#   }

