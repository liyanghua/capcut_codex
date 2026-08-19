"""Deterministic shared image layout policy: visual_layout_policy_v1.

Every image must be preserved completely: `contain`, zero crop, bounded
upscaling, and an explicit neutral canvas fill. The same computation drives
Gate 3 review media, final rendering, and the visual layout report.
"""

from __future__ import annotations

from typing import Any

LAYOUT_POLICY_VERSION = "visual_layout_policy_v1"
MAX_UPSCALE_FACTOR = 2.0
MIN_TEXT_HEIGHT_PX = 18.0
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
NEUTRAL_BACKGROUND_COLOR = "black"
PRODUCTION_CANVAS = (1080, 1920)


class ImageLayoutPolicyError(ValueError):
    """Raised when layout inputs are invalid."""


def compute_layout(
    *,
    source_width: int | None,
    source_height: int | None,
    canvas_width: int,
    canvas_height: int,
    overlay_detected: bool = False,
    known_text_height_px: float | None = None,
) -> dict[str, Any]:
    """Compute the contain layout and readability status for one material.

    Rubric (visual_layout_policy_v1):
      blocked:      crop > 0, effective upscale over 2.0x, or a known text
                    region rendered below 18px;
      manual_review: overlay detected without a reliable text region size,
                    or source dimensions missing;
      passed:      no crop, upscale at most 2.0x, and no overlay (or a text
                    region at least 18px tall).
    """
    if min(canvas_width, canvas_height) <= 0:
        raise ImageLayoutPolicyError("canvas dimensions must be positive")
    if not isinstance(source_width, int) or not isinstance(source_height, int) or min(source_width, source_height) <= 0:
        return {
            "content_rect": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
            "scale_factor": 0.0,
            "crop_pixels": 0,
            "overlay_policy": "contain",
            "readability_status": "manual_review",
            "suggestion": "素材画像缺少可判定的尺寸信息，请补充高清素材或更换已批准候选。",
        }
    scale = min(canvas_width / source_width, canvas_height / source_height)
    content_width = round(source_width * scale, 2)
    content_height = round(source_height * scale, 2)
    x = round((canvas_width - content_width) / 2, 2)
    y = round((canvas_height - content_height) / 2, 2)
    crop_pixels = 0
    if scale > MAX_UPSCALE_FACTOR:
        status = "blocked"
        suggestion = f"有效放大倍数 {scale:.2f}x 超过 {MAX_UPSCALE_FACTOR}x 上限，请补充高清素材或更换已批准候选。"
    elif overlay_detected and known_text_height_px is None:
        status = "manual_review"
        suggestion = "检测到源文字/水印但没有可靠文字区域尺寸，请人工确认可读性或更换已批准候选。"
    elif overlay_detected and known_text_height_px * scale < MIN_TEXT_HEIGHT_PX:
        status = "blocked"
        suggestion = f"文字区域渲染高度低于 {MIN_TEXT_HEIGHT_PX:.0f}px，请补充高清素材或更换已批准候选。"
    else:
        status = "passed"
        suggestion = ""
    return {
        "content_rect": {"x": x, "y": y, "w": content_width, "h": content_height},
        "scale_factor": round(scale, 4),
        "crop_pixels": crop_pixels,
        "overlay_policy": "contain",
        "readability_status": status,
        "suggestion": suggestion,
    }


def contain_filter(*, canvas_width: int, canvas_height: int) -> str:
    """FFmpeg video filter that scales down and pads without cropping."""
    if min(canvas_width, canvas_height) <= 0:
        raise ImageLayoutPolicyError("canvas dimensions must be positive")
    return (
        f"scale={canvas_width}:{canvas_height}:force_original_aspect_ratio=decrease,"
        f"pad={canvas_width}:{canvas_height}:(ow-iw)/2:(oh-ih)/2:color={NEUTRAL_BACKGROUND_COLOR}"
    )


def render_filter_for_media(
    *, suffix: str, overlay_policy: str | None, canvas_width: int, canvas_height: int
) -> str:
    """Return the layout filter shared by review media and final rendering."""
    if suffix.lower() in IMAGE_EXTENSIONS or overlay_policy == "retain_source_text":
        return contain_filter(canvas_width=canvas_width, canvas_height=canvas_height)
    return (
        f"scale={canvas_width}:{canvas_height}:force_original_aspect_ratio=increase,"
        f"crop={canvas_width}:{canvas_height}"
    )




__all__ = [
    "LAYOUT_POLICY_VERSION",
    "MAX_UPSCALE_FACTOR",
    "MIN_TEXT_HEIGHT_PX",
    "NEUTRAL_BACKGROUND_COLOR",
    "PRODUCTION_CANVAS",
    "ImageLayoutPolicyError",
    "compute_layout",
    "contain_filter",
    "render_filter_for_media",
]
