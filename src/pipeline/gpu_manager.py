"""GPU and VRAM lifecycle management.

Handles sequential model loading/unloading to stay within VRAM limits.
"""

import gc
import logging
from typing import Optional

import torch

from src.utils.gpu import get_free_vram_mb

logger = logging.getLogger("animedub.gpu_manager")


class GPUManager:
    """Manage GPU memory for sequential model loading."""

    def __init__(self, device: str = "cuda", vram_limit_mb: int = 0):
        self.device = device
        self.vram_limit_mb = vram_limit_mb
        self._current_model: Optional[str] = None
        self._model_ref = None

    def can_load(self, required_vram_mb: int) -> bool:
        """Check if enough VRAM is available."""
        if self.device == "cpu":
            return True
        free = get_free_vram_mb()
        logger.debug(f"VRAM check: need {required_vram_mb}MB, have {free}MB free")
        return free >= required_vram_mb

    def unload_current(self) -> None:
        """Unload current model and free VRAM."""
        if self._current_model:
            logger.info(f"Unloading model: {self._current_model}")
            del self._model_ref
            self._model_ref = None
            self._current_model = None
            gc.collect()
            if self.device == "cuda":
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            logger.info(f"VRAM freed. Available: {get_free_vram_mb()}MB")

    def register_model(self, name: str, model_ref) -> None:
        """Register a loaded model for lifecycle tracking."""
        self._current_model = name
        self._model_ref = model_ref
        logger.info(f"Model registered: {name}")

    @property
    def current_model(self) -> Optional[str]:
        return self._current_model

    def status(self) -> dict:
        """Get current GPU status."""
        return {
            "device": self.device,
            "current_model": self._current_model,
            "vram_free_mb": get_free_vram_mb() if self.device == "cuda" else None,
        }
