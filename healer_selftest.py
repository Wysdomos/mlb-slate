"""
healer_selftest.py — TEMPORARY end-to-end probe for the self-healing pipeline.

This file raises a runtime error on purpose so the Firebase auto-healer has a
real traceback (with a real repo filename) to parse, fetch, and open a fix PR for.
Safe to delete once the Phase 2 live test is verified.
"""


def main():
    # Intentional ValueError to produce a traceback pointing at this file.
    total = int("not_a_number")
    print(f"Total: {total}")


if __name__ == "__main__":
    main()
