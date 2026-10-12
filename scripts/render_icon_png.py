"""plugin/assets/icon.svg와 같은 도형을 PNG로 그린다(ChatGPT 아이콘 업로드용: PNG, 10KB 이하)."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
SS = 4  # 안티앨리어싱용 확대 배율
S = SIZE * SS / 128  # SVG 좌표(128) → 픽셀

img = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, SIZE * SS - 1, SIZE * SS - 1], radius=int(28 * S), fill="#163b46")


def line(points, color, width):
    pts = [(x * S, y * S) for x, y in points]
    w = int(width * S)
    d.line(pts, fill=color, width=w, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)


line([(23, 60), (64, 26), (105, 60)], "#f5efe2", 9)
line([(34, 55), (34, 102), (94, 102), (94, 55)], "#f5efe2", 9)
line([(53, 77), (75, 77)], "#67d3af", 8)
line([(64, 66), (64, 88)], "#67d3af", 8)

out = Path(__file__).resolve().parents[1] / "plugin/assets/icon.png"
img.resize((SIZE, SIZE), Image.LANCZOS).quantize(colors=32).save(out, optimize=True)
print(out, out.stat().st_size, "bytes")
