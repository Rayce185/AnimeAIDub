"""Configuration loader."""

from pathlib import Path
from typing import Any

import yaml


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML configuration file."""
    with open(path) as f:
        return yaml.safe_load(f)
