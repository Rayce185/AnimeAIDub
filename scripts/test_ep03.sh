#!/bin/bash
set -euo pipefail
# Description: First test run of AnimeAIDub pipeline against Adam's Sweet Agony EP03
# Created: 2026-02-20
# Usage: bash scripts/test_ep03.sh

# ── Configuration ─────────────────────────────────────────────────────
INPUT="/media/Hentai/Adam's Sweet Agony (2024) {tvdb-442084}/Season S01/Adam's Sweet Agony - S01E03 [JA] Bluray-1080p x264 T3KSEX.mkv"
OUTPUT="/output/Adams_Sweet_Agony_S01E03_dubbed.mkv"
MODELS_DIR="/models"
WORK_DIR="/work/test_ep03"

echo "=== AnimeAIDub Test Run ==="
echo "Input:  $INPUT"
echo "Output: $OUTPUT"
echo "Models: $MODELS_DIR"
echo "Work:   $WORK_DIR"
echo ""

# ── Verify prerequisites ─────────────────────────────────────────────
echo "Checking GPU..."
python3 -c "import torch; assert torch.cuda.is_available(), 'No GPU!'; print(f'GPU: {torch.cuda.get_device_name(0)}')"

echo "Checking models..."
if [ ! -d "$MODELS_DIR/Fun-CosyVoice3-0.5B" ]; then
    echo "ERROR: CosyVoice3 model not found. Run: docker compose run --rm download-models"
    exit 1
fi

echo "Checking input file..."
if [ ! -f "$INPUT" ]; then
    echo "ERROR: Input file not found: $INPUT"
    exit 1
fi

echo ""
echo "=== Starting pipeline ==="
python3 -m pipeline.dub_episode \
    --input "$INPUT" \
    --output "$OUTPUT" \
    --target-lang en \
    --sub-lang en \
    --models-dir "$MODELS_DIR" \
    --work-dir "$WORK_DIR" \
    --device cuda \
    --verbose

echo ""
echo "=== Test complete ==="
echo "Output: $OUTPUT"
