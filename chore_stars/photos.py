from pathlib import Path

from PIL import Image, ImageOps


def week_dir(root: Path, week_start: str, grab_id: int) -> Path:
    path = root / week_start / str(grab_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_jpeg(upload, dest: Path, thumb: Path, max_edge: int = 2400) -> None:
    image = Image.open(upload.file)
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image.thumbnail((max_edge, max_edge))
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, "JPEG", quality=85, optimize=True)
    preview = image.copy()
    preview.thumbnail((480, 480))
    preview.save(thumb, "JPEG", quality=80, optimize=True)
