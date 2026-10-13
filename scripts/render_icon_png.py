"""plugin/assets/icon.svg와 같은 도형을 PNG로 그린다(ChatGPT 아이콘 업로드용: PNG, 10KB 이하)."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
SS = 4  # 안티앨리어싱용 확대 배율
S = SIZE * SS / 128  # SVG 좌표(128) → 픽셀
BG, HOUSE, ACCENT = "#dbeafe", "#1d4ed8", "#f59e0b"

img = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, SIZE * SS - 1, SIZE * SS - 1], radius=int(28 * S), fill=BG)


def line(points, color, width):
    pts = [(x * S, y * S) for x, y in points]
    w = int(width * S)
    d.line(pts, fill=color, width=w, joint="curve")
    for p in pts:  # 꺾이는 점까지 둥글게(stroke-linejoin=round)
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)


line([(23, 60), (64, 26), (105, 60)], HOUSE, 10)
line([(34, 55), (34, 100), (94, 100), (94, 55)], HOUSE, 10)
d.ellipse([86 * S, 28 * S, 98 * S, 40 * S], fill=ACCENT)
# ₩: W 한 획 + 가로줄 두 개(글꼴 대신 선으로 그려 SVG와 똑같이 맞춘다)
line([(50, 64), (56, 88), (64, 68), (72, 88), (78, 64)], ACCENT, 5)
line([(47, 73), (81, 73)], ACCENT, 5)
line([(47, 80), (81, 80)], ACCENT, 5)

out = Path(__file__).resolve().parents[1] / "plugin/assets/icon.png"
img.resize((SIZE, SIZE), Image.LANCZOS).quantize(colors=32).save(out, optimize=True)
print(out, out.stat().st_size, "bytes")
