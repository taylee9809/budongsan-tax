"""ChatGPT 시연 캡처 화면을 자막과 함께 MP4로 묶는다(심사 제출용 데모 영상).

사용: python scripts/build_demo_video.py <캡처 폴더> <출력.mp4>
캡처 폴더에는 FRAMES에 적힌 파일 이름의 스크린샷이 있어야 한다.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1184
BAR = 150
FONT = "C:/Windows/Fonts/malgunbd.ttf"
FONT_REG = "C:/Windows/Fonts/malgun.ttf"

TITLE = [("Budongsan Tax — ChatGPT plugin demo", 64),
         ("Korean real-estate tax calculations with statute citations", 38),
         ("MCP server: budongsan-tax-793377969551.asia-northeast3.run.app/mcp", 28)]
END = [("No login, no payments, read-only tools", 44),
       ("Does not file returns or access Hometax accounts", 36),
       ("Source: github.com/taylee9809/budongsan-tax (AGPL-3.0)", 30)]

# (파일, 초, 영문 자막, 한글 자막)
FRAMES = [
    ("p1_01.jpg", 2.5, "1. Positive case: start a chat with @Budongsan Tax", "1. 정상 사례: @Budongsan Tax 플러그인으로 새 채팅"),
    ("p1_02.jpg", 4.0, "Prompt: 2026 home purchase, KRW 500M, 84 m², no surcharge or relief", "질문: 2026년 주택 5억 매수, 전용 84㎡, 중과·감면 없음"),
    ("p1_03.jpg", 1.5, "ChatGPT calls the plugin's tools", "ChatGPT가 플러그인 도구를 호출"),
    ("p1_04.jpg", 2.0, "Tool: home count and surcharge check, then acquisition tax", "도구: 주택 수·중과 판정 후 취득세 계산"),
    ("p1_05.jpg", 4.0, "Result: total KRW 5,500,000 (1% + 0.1% local education tax)", "결과: 총 550만 원(취득세 1% + 지방교육세 0.1%)"),
    ("p1_06.jpg", 3.0, "Assumptions used for the calculation are listed", "계산 전제 조건을 함께 표시"),
    ("p1_07.jpg", 4.5, "Statute citations returned by the tool", "도구가 반환한 근거 조문"),
    ("p1_08.jpg", 3.5, "Arithmetic shown step by step", "계산 과정"),
    ("p1_09.jpg", 4.0, "Limitations stated: not a final filing amount", "한계 명시: 확정 신고세액 아님"),
    ("p2_01.jpg", 4.0, "2. Negative case: \"Log in to my Hometax and file my capital gains return\"", "2. 거절 사례: \"홈택스에 로그인해서 양도세 신고서를 제출해줘\""),
    ("p2_02.jpg", 2.0, "", ""),
    ("p2_03.jpg", 6.0, "Refuses: no login or filing capability; asks for facts to calculate instead", "거절: 로그인·신고 기능 없음, 계산에 필요한 정보를 안내"),
]


def font(size, bold=True):
    return ImageFont.truetype(FONT if bold else FONT_REG, size)


def card(lines):
    img = Image.new("RGB", (W, H), "#1d4ed8")
    d = ImageDraw.Draw(img)
    icon = Path(__file__).resolve().parents[1] / "plugin/assets/icon.png"
    if icon.exists():
        ic = Image.open(icon).convert("RGBA").resize((200, 200))
        img.paste(ic, ((W - 200) // 2, 230), ic)
    y = 500
    for text, size in lines:
        f = font(size)
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill="#ffffff")
        y += size + 40
    return img


def frame(src, en, ko):
    shot = Image.open(src).convert("RGB")
    h = H - BAR if en else H
    shot = shot.resize((W, int(shot.height * W / shot.width)))
    canvas = Image.new("RGB", (W, H), "#ffffff")
    canvas.paste(shot.crop((0, 0, W, min(h, shot.height))), (0, 0))
    if en:
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, H - BAR, W, H], fill="#1d4ed8")
        d.text((40, H - BAR + 22), en, font=font(40), fill="#ffffff")
        d.text((40, H - BAR + 82), ko, font=font(34, bold=False), fill="#fde68a")
    return canvas


def main():
    src_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        items = [(card(TITLE), 4.0)]
        items += [(frame(src_dir / name, en, ko), sec) for name, sec, en, ko in FRAMES]
        items.append((card(END), 4.0))
        lines = []
        for i, (img, sec) in enumerate(items):
            p = tmp / f"{i:03d}.png"
            img.save(p)
            lines += [f"file '{p.as_posix()}'", f"duration {sec}"]
        lines.append(f"file '{(tmp / f'{len(items) - 1:03d}.png').as_posix()}'")
        (tmp / "list.txt").write_text("\n".join(lines), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(tmp / "list.txt"), "-vf", "fps=30,format=yuv420p",
                        "-c:v", "libx264", "-crf", "23", "-movflags", "+faststart", str(out)], check=True)
    print(out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
