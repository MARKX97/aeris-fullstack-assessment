"""Generate placeholder product images for the Variant PDP (spec §4).

Pure standard library (zlib + struct): no Pillow dependency. Writes
360x360 RGB PNGs into ../public/images/, one per SKU (colour-coded
background with the size letter) plus a neutral ``placeholder.png`` used
before any variant is selected.

Usage (from this directory):
    python3 gen_placeholders.py
"""

from __future__ import annotations

import binascii
import struct
import zlib
from pathlib import Path

SIZE = 360
OUT_DIR = Path(__file__).resolve().parent.parent / "public" / "images"

# 5x7 bitmap letters, scaled up when drawn.
FONT = {
    "S": ["01110", "10001", "10000", "01110", "00001", "10001", "01110"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
}

COLOURS = {
    "red": ((245, 199, 193), (176, 58, 46)),
    "blue": ((199, 215, 240), (46, 95, 158)),
    "green": ((203, 231, 206), (46, 125, 50)),
}

SKUS = [
    ("sku-red-s", "red", "S"),
    ("sku-red-m", "red", "M"),
    ("sku-red-l", "red", "L"),
    ("sku-blue-s", "blue", "S"),
    ("sku-blue-m", "blue", "M"),
    ("sku-green-s", "green", "S"),
    ("sku-green-m", "green", "M"),
    ("sku-green-l", "green", "L"),
]


def write_png(path: Path, pixels: list[list[tuple[int, int, int]]]) -> None:
    """Minimal PNG encoder: 8-bit RGB, no interlace, one IDAT chunk."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\x00" + b"".join(struct.pack("BBB", *px) for px in row) for row in pixels
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def render(bg: tuple[int, int, int], fg: tuple[int, int, int] | None, letter: str | None) -> list[list[tuple[int, int, int]]]:
    px = [[bg] * SIZE for _ in range(SIZE)]
    if letter and fg:
        cell = 40
        glyph = FONT[letter]
        w, h = len(glyph[0]) * cell, len(glyph) * cell
        x0, y0 = (SIZE - w) // 2, (SIZE - h) // 2
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    for y in range(y0 + gy * cell, y0 + (gy + 1) * cell):
                        for x in range(x0 + gx * cell, x0 + (gx + 1) * cell):
                            px[y][x] = fg
    return px


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sku_id, colour, letter in SKUS:
        bg, fg = COLOURS[colour]
        write_png(OUT_DIR / f"{sku_id}.png", render(bg, fg, letter))
        print(f"wrote {sku_id}.png")
    write_png(OUT_DIR / "placeholder.png", render((232, 232, 232), None, None))
    print("wrote placeholder.png")


if __name__ == "__main__":
    main()
