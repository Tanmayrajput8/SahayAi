"""Standalone CLI Script for Running Fairness & Model Evaluation.

Usage:
    py scripts/run_fairness_eval.py
"""
import sys
import os
import json

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.fairness_eval import run_fairness_evaluation
from app.db.session import SessionLocal


def main():
    print("=" * 70)
    print(" SahayAI Emergency: Multilingual Fairness & Evaluation Benchmark ")
    print("=" * 70)
    print("Evaluating triage model across English, Hindi, Marathi, and Code-Mixed inputs...\n")

    db = SessionLocal()
    try:
        report = run_fairness_evaluation(db=db)
    finally:
        db.close()

    overall = report["overall_metrics"]
    print(f"Total Labeled Samples : {overall['total_test_samples']}")
    print(f"Overall Severity Acc  : {overall['overall_severity_accuracy'] * 100:.1f}%")
    print(f"Overall Ambulance Acc : {overall['overall_ambulance_accuracy'] * 100:.1f}%")
    print(f"Location Extraction   : {overall['overall_location_extraction_rate'] * 100:.1f}%")
    print(f"Max Severity Disparity: {report['max_severity_disparity'] * 100:.1f}%")
    print(f"Disparity Flagged     : {report['disparity_flagged']}")
    print("\n" + "-" * 70)
    print(" BREAKDOWN BY LANGUAGE SUBGROUP")
    print("-" * 70)
    print(f"{'Language':<15} {'Samples':<8} {'Severity Acc':<14} {'Ambulance Acc':<15} {'Avg Latency'}")
    print("-" * 70)

    for lang, metrics in report["language_breakdown"].items():
        print(
            f"{lang:<15} "
            f"{metrics['total_cases']:<8} "
            f"{metrics['severity_accuracy'] * 100:>6.1f}%        "
            f"{metrics['ambulance_accuracy'] * 100:>6.1f}%         "
            f"{metrics['avg_latency_ms']:>6.1f} ms"
        )
    print("-" * 70)

    # Machine-readable output
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fairness_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nMachine-readable report written to: {output_path}")


if __name__ == "__main__":
    main()
