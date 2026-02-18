"""GPU detection and VRAM management."""

import logging
import subprocess

logger = logging.getLogger("animedub.gpu")


def get_gpu_info() -> list[dict]:
    """Get available NVIDIA GPU information."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free",
             "--format=csv,nounits,noheader"],
            capture_output=True, text=True, timeout=10
        )
        gpus = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "vram_total_mb": int(parts[2]),
                "vram_used_mb": int(parts[3]),
                "vram_free_mb": int(parts[4]),
            })
        return gpus
    except Exception as e:
        logger.error(f"Failed to query GPU info: {e}")
        return []


def get_free_vram_mb(gpu_index: int = 0) -> int:
    """Get free VRAM in MB for a specific GPU."""
    gpus = get_gpu_info()
    for gpu in gpus:
        if gpu["index"] == gpu_index:
            return gpu["vram_free_mb"]
    return 0
