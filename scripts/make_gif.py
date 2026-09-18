"""Stitch the recorded frames into a looping GIF.

uv run --with pillow python scripts/make_gif.py frames docs/demo.gif
"""

import sys
from pathlib import Path

from PIL import Image


def main(frames_dir: str, out: str, width: int = 960, ms: int = 1300) -> None:
    paths = sorted(Path(frames_dir).glob("*.png"))
    frames = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        frames.append(
            im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        )
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)
    print(f"{len(frames)} frames -> {out} ({Path(out).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
