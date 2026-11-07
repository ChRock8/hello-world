"""Where to put the overlay card (no Tk needed, so it can be tested)."""


def place_card(box, card_w, card_h, screen_w, screen_h, gap=8):
    """Above the tooltip if there's room, else below, else beside it."""
    x, y, w, h = box
    cx = int(x + (w - card_w) / 2)
    if y - card_h - gap >= 0:
        pos = (cx, y - card_h - gap)
    elif y + h + gap + card_h <= screen_h:
        pos = (cx, y + h + gap)
    elif x - card_w - gap >= 0:
        pos = (x - card_w - gap, y)
    else:
        pos = (x + w + gap, y)
    return (max(0, min(pos[0], screen_w - card_w)), max(0, min(pos[1], screen_h - card_h)))
