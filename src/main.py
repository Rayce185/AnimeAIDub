"""AnimeAIDub entry point.

Starts the web server and library scanner.
"""

import logging
from pathlib import Path

import uvicorn

from src.utils.config import load_config
from src.utils.logging import setup_logging


def main():
    """Main entry point."""
    config_path = Path("/app/config.yaml")
    if not config_path.exists():
        config_path = Path("config.example.yaml")

    config = load_config(config_path)
    setup_logging(config.get("logging", {}))

    logger = logging.getLogger("animedub")
    logger.info("AnimeAIDub v0.1.0 starting...")

    web_config = config.get("web", {})
    uvicorn.run(
        "src.web.app:app",
        host=web_config.get("host", "0.0.0.0"),
        port=web_config.get("port", 29100),
        log_level="info",
    )


if __name__ == "__main__":
    main()
