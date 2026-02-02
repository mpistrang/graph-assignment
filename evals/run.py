#!/usr/bin/env python
"""CLI for running golden set evaluations.

Usage:
    python -m evals.run                     # Run all test cases
    python -m evals.run --category routing  # Run specific category
    python -m evals.run --case GS-04        # Run single case
    python -m evals.run --output results/   # Save results to file
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from evals.evaluator import TriageEvaluator, print_report, save_report
from src.main import load_mock_data, run_triage


def main():
    parser = argparse.ArgumentParser(description="Run golden set evaluations")
    parser.add_argument(
        "--golden-set",
        default="evals/golden_set.yaml",
        help="Path to golden set YAML file",
    )
    parser.add_argument(
        "--category",
        help="Run only cases in this category",
    )
    parser.add_argument(
        "--case",
        help="Run only this specific case ID",
    )
    parser.add_argument(
        "--output",
        help="Save results to this directory or file",
    )
    parser.add_argument(
        "--mock-data",
        default="data/mock_intercom.yaml",
        help="Path to mock Intercom data",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed output",
    )

    args = parser.parse_args()

    # Load environment
    load_dotenv()

    # Load mock data
    print(f"Loading mock data from {args.mock_data}...")
    mock_data = load_mock_data(args.mock_data)

    # Create evaluator
    print(f"Loading golden set from {args.golden_set}...")
    evaluator = TriageEvaluator(args.golden_set)

    # Filter cases if requested
    if args.category:
        evaluator.cases = [c for c in evaluator.cases if c["category"] == args.category]
        print(f"Filtered to {len(evaluator.cases)} cases in category '{args.category}'")

    if args.case:
        evaluator.cases = [c for c in evaluator.cases if c["id"] == args.case]
        print(f"Running single case: {args.case}")

    if not evaluator.cases:
        print("No test cases to run!")
        sys.exit(1)

    print(f"\nRunning {len(evaluator.cases)} test cases...\n")
    print("-" * 80)

    # Run evaluation
    report = evaluator.run_all(run_triage, mock_data)

    print("-" * 80)
    print()

    # Print report
    print_report(report)

    # Save results if requested
    if args.output:
        output_path = Path(args.output)
        if output_path.is_dir():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_path / f"eval_results_{timestamp}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_report(report, str(output_path))
        print(f"\nResults saved to {output_path}")

    # Exit with error code if any cases failed
    sys.exit(0 if report.pass_rate == 1.0 else 1)


if __name__ == "__main__":
    main()
