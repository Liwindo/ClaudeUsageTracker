"""Entry point: python -m claude_usage_monitor"""

from __future__ import annotations

import logging
import sys

from .config import Config


def main() -> None:
    config = Config.load()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Import App here so logging is configured first.
    from .app import App

    try:
        App(config).run()
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("Fatal error — application will exit.")
        sys.exit(1)


if __name__ == "__main__":
    main()
