"""Read-only CLI for DEMO account export consistency checks."""
from __future__ import annotations

import argparse
import json

from research.paper_account_audit import audit_paper_account


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit DEMO account evidence without broker access")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--intents", required=True)
    parser.add_argument("--fills", required=True)
    args = parser.parse_args()
    report = audit_paper_account(args.manifest, args.intents, args.fills)
    print(json.dumps(report.as_dict(), sort_keys=True, indent=2))
    return 0 if report.eligible_for_external_review else 1


if __name__ == "__main__":
    raise SystemExit(main())
