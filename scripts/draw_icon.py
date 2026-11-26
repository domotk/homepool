"""Draw the HomePool brand icon: a pool with a ladder, in the outlined style of
the other domotk icons. Drawn at 8x and downsampled for clean edges.

    pip install pillow
    python scripts/draw_icon.py custom_components/homepool/brand
"""
import sys
from PIL import Image, ImageDraw

S = 8
W = 512 * S
OUT = 14 * S  # outline width

def draw(size_out, path):
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (38, 50, 56, 255)
    # Coping: a stone border, slightly perspective (wider at the bottom).
    coping = [(70*S, 120*S), (442*S, 120*S), (478*S, 430*S), (34*S, 430*S)]
    d.polygon(coping, fill=(236, 239, 241, 255), outline=ink, width=OUT)
    # Water.
    water = [(108*S, 158*S), (404*S, 158*S), (430*S, 392*S), (82*S, 392*S)]
    d.polygon(water, fill=(38, 166, 212, 255), outline=ink, width=OUT)
    # Deep end shading.
    deep = [(108*S, 158*S), (404*S, 158*S), (409*S, 205*S), (103*S, 205*S)]
    d.polygon(deep, fill=(25, 130, 180, 255))
    d.line([(108*S, 158*S), (404*S, 158*S)], fill=ink, width=OUT)
    # Waves.
    for y, x0, x1 in ((250, 130, 300), (300, 170, 360), (345, 120, 260)):
        pts = []
        for i in range(0, 41):
            x = x0 + (x1 - x0) * i / 40
            import math
            pts.append((x*S, (y + 10*math.sin(i/40*math.pi*3))*S))
        d.line(pts, fill=(178, 235, 242, 255), width=12*S, joint="curve")
    # Ladder: two rails curving over the coping, three steps.
    rail = (176, 190, 197, 255)
    for x in (318, 372):
        d.line([(x*S, 95*S), (x*S, 300*S)], fill=ink, width=30*S)
        d.line([(x*S, 95*S), (x*S, 300*S)], fill=rail, width=16*S)
        d.ellipse([(x-20)*S, 70*S, (x+20)*S, 110*S], fill=rail, outline=ink, width=8*S)
    for y in (200, 245, 290):
        d.rectangle([318*S, (y-8)*S, 372*S, (y+8)*S], fill=rail, outline=ink, width=6*S)
    img = img.resize((size_out, size_out), Image.LANCZOS)
    img.save(path)

base = sys.argv[1]
draw(256, f"{base}/icon.png")
draw(512, f"{base}/icon@2x.png")
