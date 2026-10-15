"""Image loading and compositing shared by the cutout and upscale steps."""

from pathlib import Path

from PIL import Image, ImageOps

_heif_registered = False


def load_rgb(path: Path) -> Image.Image:
    """Open jpg/png/webp/heic, apply EXIF rotation, flatten to RGB."""
    global _heif_registered
    if not _heif_registered:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _heif_registered = True
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
            return flat
        return img.convert("RGB")


def padded_box(bbox: tuple[int, int, int, int], padding: float) -> tuple[int, int, int, int]:
    """Grow a bbox by `padding` × its long edge on every side (may exceed image bounds)."""
    left, top, right, bottom = bbox
    pad = round(max(right - left, bottom - top) * padding)
    return left - pad, top - pad, right + pad, bottom + pad


def compose(rgb: Image.Image, mask: Image.Image, background: str) -> Image.Image:
    """Put the masked product on white, or keep it on a transparent canvas."""
    if background == "transparent":
        out = rgb.convert("RGBA")
        out.putalpha(mask)
        return out
    return Image.composite(rgb, Image.new("RGB", rgb.size, (255, 255, 255)), mask)
