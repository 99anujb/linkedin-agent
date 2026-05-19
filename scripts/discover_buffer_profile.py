"""One-time helper: print Buffer profile IDs for each connected channel.

Usage:
    python -m scripts.discover_buffer_profile
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from agent.delivery.buffer import list_profiles


def main() -> int:
    load_dotenv()
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        print("BUFFER_ACCESS_TOKEN missing in environment / .env", file=sys.stderr)
        return 1
    profiles = list_profiles(access_token=token)
    if not profiles:
        print("No connected channels found.", file=sys.stderr)
        return 1
    print("service\tid\tusername")
    for p in profiles:
        print(f"{p.service}\t{p.id}\t{p.username}")
    print(
        "\nCopy the `id` for service=linkedin into .env as " "BUFFER_LINKEDIN_PROFILE_ID.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
