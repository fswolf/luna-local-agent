import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
PW, PH = 1024, 1536                       # one page; the image is two side by side
F = '/usr/share/fonts/truetype/freefont/'
body = ImageFont.truetype(F + 'FreeSerif.ttf', 36)
ital = ImageFont.truetype(F + 'FreeSerifItalic.ttf', 30)
head = ImageFont.truetype(F + 'FreeSerifBold.ttf', 44)
cap = ImageFont.truetype(F + 'FreeSerifBold.ttf', 118)
small = ImageFont.truetype(F + 'FreeSerifItalic.ttf', 28)
INK = (52, 34, 40)

LEFT = [
 "Every night, when the last reader had gone home and the great doors of the Moonlit Library sighed shut, a small black cat named Ink climbed the spiral stair to the highest shelf.",
 "Nobody had given Ink the job. Nobody had to. Someone, Ink felt, ought to make sure the lamps were lit for the books, because books do their dreaming after dark, and a book that dreams in the dark dreams of being forgotten.",
 "So Ink went from lamp to lamp, nudging each little flame awake with a careful paw, and the shelves glowed gold, one row after another, until the whole library hummed like a hive.",
 "The atlases murmured about coastlines. The cookbooks smelled faintly of cinnamon and burnt sugar. Somewhere in the history section, a very old book sneezed, and dust drifted down through the lamplight like snow.",
]
RIGHT = [
 "Tonight, though, one lamp would not wake.",
 "It sat at the very end of the poetry aisle, cold and grey, beside a thin blue book Ink had never noticed before. Ink pawed at the lamp. Nothing. Ink breathed on it, which sometimes worked. Nothing.",
 "Then the blue book opened all by itself, just a crack, and a voice no louder than a page turning said, “Please don’t. I like the dark. It’s the only time anyone sits with me.”",
 "Ink considered this for a long moment. Then Ink curled up on the shelf beside the book, tail over nose, and stayed.",
 "“Read me something,” said Ink.",
 "And so, for the first time in a hundred years, the little blue book read aloud: a poem about the moon, who was also small, and also lonely, and who also kept a light on for the ones who stayed up late.",
 "By morning the lamp was still dark. But the shelf beside it had never been warmer.",
]

def paper(seed):
    random.seed(seed)
    im = Image.new('RGB', (PW, PH), (241, 231, 208))
    n = Image.effect_noise((PW, PH), 14).convert('L')
    im = Image.blend(im, Image.merge('RGB', [n, n, n]).point(lambda v: v), 0.05)
    # warm darkening toward the edges and the gutter
    shade = Image.new('L', (PW, PH), 0); d = ImageDraw.Draw(shade)
    for i in range(60):
        d.rectangle([i, i, PW - 1 - i, PH - 1 - i], outline=int(70 * (1 - i / 60) ** 2))
    shade = shade.filter(ImageFilter.GaussianBlur(18))
    return Image.composite(Image.new('RGB', (PW, PH), (196, 172, 130)), im, shade)

def wrap(d, text, font, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=font) <= width: cur = t
        else: lines.append(cur); cur = w
    lines.append(cur); return lines

def justify(d, x, y, line, font, width, last):
    if last or ' ' not in line:
        d.text((x, y), line, font=font, fill=INK); return
    words = line.split(); gap = (width - sum(d.textlength(w, font=font) for w in words)) / (len(words) - 1)
    for w in words:
        d.text((x, y), w, font=font, fill=INK); x += d.textlength(w, font=font) + gap

def page(paras, num, left, heading=None):
    im = paper(num); d = ImageDraw.Draw(im)
    mx_out, mx_in, top = 120, 150, 170
    x0 = mx_out if left else mx_in; width = PW - mx_out - mx_in
    y = top
    d.text((PW / 2 + (-15 if left else 15), 92), 'THE MOONLIT LIBRARY' if left else 'The Cat Who Kept the Lamps',
           font=small, fill=(120, 90, 90), anchor='mm')
    if heading:
        y += 30
        d.text((PW / 2 + (-15 if left else 15), y), heading[0], font=small, fill=(120, 90, 90), anchor='mm'); y += 60
        d.text((PW / 2 + (-15 if left else 15), y), heading[1], font=head, fill=INK, anchor='mm'); y += 50
        d.text((PW / 2 + (-15 if left else 15), y), '❦', font=head, fill=(150, 110, 60), anchor='mm'); y += 70
    lh = 52
    for pi, para in enumerate(paras):
        indent = 0 if (pi == 0) else 44
        if pi == 0 and heading:                  # drop cap
            d.text((x0, y - 10), para[0], font=cap, fill=(110, 60, 90))
            cw = d.textlength(para[0], font=cap) + 12
            rest = para[1:]
            first = wrap(d, rest, body, width - cw)
            for i, ln in enumerate(first[:2]):
                justify(d, x0 + cw, y + i * lh, ln, body, width - cw, False)
            remaining = ' '.join(' '.join(first[2:]).split())
            lines = wrap(d, remaining, body, width) if remaining else []
            y += 2 * lh
        else:
            lines = wrap(d, para, body, width - indent)
            justify(d, x0 + indent, y, lines[0], body, width - indent, len(lines) == 1)
            y += lh; lines = lines[1:]
        for i, ln in enumerate(lines):
            justify(d, x0, y, ln, body, width, i == len(lines) - 1); y += lh
        y += 10
    if not left and y < PH - 260:                 # the end of the chapter, if there's room
        d.text((PW / 2 + 15, y + 50), '\u2042', font=head, fill=(150, 110, 60), anchor='mm')
    d.text((x0 if left else PW - mx_out, PH - 110), str(num), font=small, fill=(120, 90, 90), anchor='lm' if left else 'rm')
    return im, y

l, yl = page(LEFT, 112, True, ('Chapter Seven', 'The Cat Who Kept the Lamps'))
r, yr = page(RIGHT, 113, False)
print('text ends at', yl, yr, 'of', PH - 140)
out = Image.new('RGB', (2 * PW, PH)); out.paste(l, (0, 0)); out.paste(r, (PW, 0))
out.save('book_pages.png')
