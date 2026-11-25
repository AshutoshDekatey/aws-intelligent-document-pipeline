"""Regenerate the synthetic scan. Requires Pillow and DejaVu Sans."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1] / 'examples/v02'
lines = (root / 'scanned-reference.txt').read_text().splitlines()
image = Image.new('L', (1800, 1050), color=248)
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('DejaVuSans.ttf', 36)
bold = ImageFont.truetype('DejaVuSans-Bold.ttf', 40)
for index, line in enumerate(lines):
    draw.text((100, 90 + index * 75), line, font=bold if index == 0 else font, fill=20)
image.rotate(0.35, resample=Image.Resampling.BICUBIC, fillcolor=248).save(root / 'scanned.png')
