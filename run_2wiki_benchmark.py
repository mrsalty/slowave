#!/usr/bin/env python3
"""
Run 2WikiMultiHopQA benchmark and compare against HippoRAG baselines.

Usage:
  python run_2wiki_benchmark.py                    # Run on full 100-example dataset
  python run_2wiki_benchmark.py --num-examples 20  # Run on subset
  python run_2wiki_benchmark.py --dataset PATH     # Run on custom dataset file
"""

import argparse
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from tests.integration.hipporag_qa_eval import (
    run_2wiki_benchmark,
    load_2wiki_multihop_json,
    SlowaveQAEvaluator,
    BenchmarkResults,
    HIPPORAG_BASELINES,
)


def main():
    parser = argparse.ArgumentParser(
        description="Run 2WikiMultiHopQA benchmark against HippoRAG baselines"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="tests/integration/datasets/2wiki_multihop_100.json",
        help="Path to dataset JSON file",
    )
    parser.add_argument(
        "--num-examples",
        type=int,
        default=None,
        help="Limit to this many examples (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results/hipporag_comparison",
        help="Directory to save results",
    )

    args = parser.parse_args()

    dataset_file = Path(args.dataset)
    if not dataset_file.exists():
        print(f"❌ Dataset file not found: {dataset_file}")
        print("\nExpected location: tests/integration/datasets/2wiki_multihop_100.json")
        print("\nTo download the dataset, run:")
        print("  python -c \"from datasets import load_dataset; ...")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("2WikiMultiHopQA Benchmark: Slowave vs HippoRAG")
    print("=" * 70)

    # Run benchmark
    results_file = run_2wiki_benchmark(
        str(dataset_file),
        num_examples=args.num_examples,
    )

    print(f"\n✓ Benchmark complete!")
    print(f"  Results saved: {results_file}")


if __name__ == "__main__":
    main()
