#!/usr/bin/env python3
"""Pixel loyalty hearts next to living companion portraits."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "game" / "delve" / "portraits"
SCALE = 3  # 16 -> 48

# 16x16 fill mask, classic pixel heart.
FILL = [
    "................",
    "................",
    "....##....##....",
    "...####..####...",
    "..##############",
    ".##############.",
    ".##############.",
    ".##############.",
    "..############..",
    "...##########...",
    "....########....",
    ".....######.....",
    "......####......",
    ".......##.......",
    "................",
    "................",
]


def parse(mask: list[str]) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for y, row in enumerate(mask):
        if len(row) != 16:
            raise ValueError(f"row {y} len {len(row)}")
        for x, ch in enumerate(row):
            if ch == "#":
                cells.add((x, y))
    return cells


def neighbors8(x: int, y: int) -> list[tuple[int, int]]:
    return [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def outline_of(fill: set[tuple[int, int]]) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for x, y in fill:
        for nx, ny in neighbors8(x, y):
            if (nx, ny) not in fill and 0 <= nx < 16 and 0 <= ny < 16:
                out.add((nx, ny))
    return out


def put(img: Image.Image, cells: set[tuple[int, int]], color: tuple[int, int, int, int]) -> None:
    px = img.load()
    for x, y in cells:
        if 0 <= x < 16 and 0 <= y < 16:
            px[x, y] = color


def shade(
    fill: set[tuple[int, int]],
    body: tuple[int, int, int, int],
    hi: tuple[int, int, int, int],
    shadow: tuple[int, int, int, int],
) -> Image.Image:
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    put(img, fill, body)
    hi_cells = {(x, y) for x, y in fill if y <= 6 and x <= 7 and (x + y) % 2 == 0}
    sh_cells = {(x, y) for x, y in fill if y >= 10 or x >= 11}
    put(img, sh_cells & fill, shadow)
    put(img, hi_cells & fill, hi)
    return img


def broken_heart() -> Image.Image:
    fill = parse(FILL)
    crack = {
        (7, 4),
        (8, 5),
        (7, 6),
        (8, 7),
        (7, 8),
        (8, 9),
        (7, 10),
        (8, 11),
        (7, 12),
    }
    left = {(x, y) for x, y in fill if x <= 7 and (x, y) not in crack}
    right = {(x, y) for x, y in fill if x >= 8 and (x, y) not in crack}
    # Shift halves apart.
    left = {(x - 1, y - 1) for x, y in left}
    right = {(x + 1, y + 1) for x, y in right}
    halves = left | right
    red = (196, 32, 32, 255)
    black = (18, 14, 12, 255)
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    put(img, outline_of(halves), red)
    put(img, halves, black)
    return img


def save(name: str, src: Image.Image) -> Path:
    dest = OUT / f"loyalty_heart_{name}.webp"
    big = src.resize((16 * SCALE, 16 * SCALE), Image.Resampling.NEAREST)
    dest.parent.mkdir(parents=True, exist_ok=True)
    big.save(dest, format="WEBP", lossless=True, method=6)
    return dest


def main() -> None:
    fill = parse(FILL)
    save("broken", broken_heart())
    save(
        "dim",
        shade(fill, (42, 72, 118, 255), (70, 102, 148, 255), (24, 44, 78, 255)),
    )
    save(
        "pink",
        shade(fill, (244, 176, 196, 255), (255, 214, 224, 255), (214, 132, 160, 255)),
    )
    save(
        "red",
        shade(fill, (220, 28, 36, 255), (255, 92, 88, 255), (150, 12, 22, 255)),
    )
    save(
        "gold",
        shade(fill, (232, 176, 40, 255), (255, 236, 140, 255), (176, 112, 12, 255)),
    )
    for p in sorted(OUT.glob("loyalty_heart_*.webp")):
        print(p, p.stat().st_size)


if __name__ == "__main__":
    main()
