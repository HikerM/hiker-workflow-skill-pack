#!/usr/bin/env python3
"""Basic screenshot pixel comparison.

Requires Pillow. The output is a rough metric and a grayscale difference image;
it is not a replacement for region geometry, text, control-state, or human review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError:  # pragma: no cover
    print("缺少 Pillow。请运行：pip install Pillow", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="比较两张基准尺寸一致的截图")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--output", default="screenshot-diff.png", help="灰度差异图输出路径")
    parser.add_argument("--json", dest="json_output", default=None, help="可选 JSON 指标输出路径")
    parser.add_argument("--pixel-threshold", type=int, default=10, help="像素通道差异阈值 0-255")
    args = parser.parse_args()

    baseline_path = Path(args.baseline).expanduser().resolve()
    candidate_path = Path(args.candidate).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    with Image.open(baseline_path) as img_a, Image.open(candidate_path) as img_b:
        a = img_a.convert("RGB")
        b = img_b.convert("RGB")
        if a.size != b.size:
            print(f"错误：截图尺寸不同：baseline={a.size}, candidate={b.size}", file=sys.stderr)
            return 3

        diff = ImageChops.difference(a, b)
        stat = ImageStat.Stat(diff)
        channel_means = stat.mean
        mean_absolute_error = sum(channel_means) / len(channel_means)
        similarity = max(0.0, 1.0 - mean_absolute_error / 255.0)

        gray = diff.convert("L")
        histogram = gray.histogram()
        total_pixels = a.size[0] * a.size[1]
        exact_pixels = histogram[0]
        threshold = max(0, min(255, args.pixel_threshold))
        changed_pixels = sum(histogram[threshold + 1 :])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        gray.save(output_path)

        result = {
            "baseline": str(baseline_path),
            "candidate": str(candidate_path),
            "width": a.size[0],
            "height": a.size[1],
            "mean_absolute_error_0_255": round(mean_absolute_error, 6),
            "basic_similarity_0_1": round(similarity, 8),
            "exact_pixel_ratio": round(exact_pixels / total_pixels, 8),
            "pixel_threshold": threshold,
            "changed_pixel_ratio_above_threshold": round(changed_pixels / total_pixels, 8),
            "difference_image": str(output_path),
            "warning": "基础像素指标不能单独作为视觉验收结论。",
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.json_output:
            json_path = Path(args.json_output).expanduser().resolve()
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
