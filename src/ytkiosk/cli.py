from __future__ import annotations

import argparse

from ytkiosk import doctor, legacy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ytkiosk",
        description=(
            "YTKiosk helper commands. "
            "The GUI app still runs via simple-video-player.py."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="check runtime dependencies")
    subparsers.add_parser("run", help="launch the GUI app")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor.main([])
    if args.command == "run":
        return legacy.main()

    parser.print_help()
    return 0
