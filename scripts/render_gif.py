"""Turns docs/demo/transcript.json (real tool calls) into docs/demo/mcp-lite-demo.gif.
It draws a terminal-style replay of the calls and responses. It is NOT a chat window and
no AI model is involved: it shows what the MCP endpoint returned. Long results are cut."""
import json, sys
from PIL import Image, ImageDraw, ImageFont

src, dst = sys.argv[1:3]
steps = json.load(open(src))
W, H, PAD = 980, 560, 18
font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
bold = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14, index=1)
LH = 19
BG, FG, DIM, GREEN, RED, BLUE = (22, 24, 30), (225, 228, 235), (130, 138, 150), (120, 220, 140), (255, 120, 120), (130, 180, 255)


def wrap(text, width=104):
    out = []
    for line in text.split("\n"):
        while len(line) > width:
            out.append(line[:width]); line = "  " + line[width:]
        out.append(line)
    return out


def result_lines(step):
    r = step["result"]
    if step["is_error"]:
        return [("refused: " + (r if isinstance(r, str) else json.dumps(r)), RED)]
    text = json.dumps(r, indent=1, ensure_ascii=False)
    lines = text.split("\n")
    if len(lines) > 12:
        lines = lines[:12] + ["  ... (truncated for display)"]
    return [(l, FG) for l in lines]


def call_line(step):
    args = ", ".join(f"{k}={json.dumps(v)}" for k, v in step["arguments"].items())
    return f"> {step['tool']}({args})"


feed = [("MCP Lite demo: real calls to a local Odoo 19 (sample data), via Odoo API key", DIM), ("No chat window here; this is what the endpoint returns.", DIM), ("", FG)]
frames, durations = [], []


def render(lines, cursor=True):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    view = lines[-((H - 2 * PAD) // LH):]
    y = PAD
    for text, color in view:
        d.text((PAD, y), text, font=bold if text.startswith(">") else font, fill=color)
        y += LH
    return img


frames.append(render(feed)); durations.append(1200)
for step in steps:
    cl = wrap(call_line(step))
    for i in range(1, len(cl[0]) + 1, 6):
        frames.append(render(feed + [(cl[0][:i], BLUE)] )); durations.append(40)
    feed += [(l, BLUE) for l in cl]
    frames.append(render(feed)); durations.append(400)
    for text, color in result_lines(step):
        for l in wrap(text):
            feed.append((l, color))
    feed.append(("", FG))
    frames.append(render(feed)); durations.append(2600)
frames[0].save(dst, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
print("wrote", dst, len(frames), "frames")
