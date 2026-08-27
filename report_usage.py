#!/usr/bin/env python3
"""Print cumulative Gemini API token usage and estimated cost from
usage_log.jsonl (all-time, across every session -- see game/usage.py).

Run with `python3 report_usage.py`. No API key or running app needed;
it only reads the log file.
"""

from game import usage


def main():
    totals_by_model = usage._load_totals_from_log()
    if not totals_by_model:
        print(f"No usage logged yet at {usage.LOG_PATH}")
        return

    total_cost = 0.0
    total_calls = 0
    total_input = 0
    total_output = 0

    print(f"Usage log: {usage.LOG_PATH}\n")
    for model, bucket in totals_by_model.items():
        cost = usage._cost_for(model, bucket)
        total_cost += cost
        total_calls += bucket["calls"]
        total_input += bucket["input_tokens"]
        total_output += bucket["output_tokens"]

        pricing_note = "" if model in usage.PRICING else "  (pricing unknown)"
        print(f"{model}{pricing_note}")
        print(f"  calls:  {bucket['calls']}")
        print(f"  input:  {bucket['input_tokens']:,} tokens")
        print(f"  output: {bucket['output_tokens']:,} tokens")
        print(f"  cost:   ${cost:.4f}\n")

    print("-" * 40)
    print(f"TOTAL: {total_calls} calls, {total_input + total_output:,} tokens, ${total_cost:.4f}")


if __name__ == "__main__":
    main()
