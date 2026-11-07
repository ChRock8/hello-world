"""A fake 1080p inventory screen: equipped tooltip (left), hovered tooltip (right)."""
from d3helper.ocr import OcrLine

POWER = OcrLine("Gain 1% Critical Hit Chance for each enemy", 1030, 560, 330, 16, "orange")

HOVERED = [
    OcrLine("Gauntiet of the Wastes", 1100, 300, 200, 20),          # OCR typo on purpose
    OcrLine("Ancient Set Gloves", 1105, 345, 160, 16),
    OcrLine("1,234", 1105, 370, 60, 18),
    OcrLine("Armor", 1105, 392, 50, 14),
    OcrLine("Primary", 1030, 440, 60, 14),
    OcrLine("Critical Hit Chance Increased by 9.5%", 1030, 465, 330, 16),
    OcrLine("Critical Hit Damage Increased by 48.0%", 1030, 487, 330, 16),
    OcrLine("+716 Strength", 1030, 509, 120, 16),
    OcrLine("Attack Speed Increased by 7.0%", 1030, 531, 260, 16),
    POWER,
    OcrLine("Wrath of the Wastes", 1110, 600, 180, 16),
    OcrLine("(2) Set: Whirlwind gains Rend damage", 1030, 622, 330, 16),
    OcrLine("Required Level: 70", 1030, 700, 150, 16),
]
EQUIPPED = [
    OcrLine("Equipped", 760, 270, 80, 14),
    OcrLine("Gauntlet of the Wastes", 700, 300, 200, 20),
    OcrLine("Set Gloves", 705, 345, 90, 16),
    OcrLine("Primary", 630, 440, 60, 14),
    OcrLine("+500 Strength", 630, 465, 120, 16),
    OcrLine("Critical Hit Chance Increased by 8.0%", 630, 487, 330, 16),
    OcrLine("Account Bound", 630, 560, 120, 16),
]
INVENTORY_NOISE = [OcrLine("Inventory", 1600, 100, 120, 20), OcrLine("1,234,567", 1700, 900, 90, 16)]
LINES = EQUIPPED + HOVERED + INVENTORY_NOISE
CURSOR = (1600, 420)


def image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1920, 1080))
    ImageDraw.Draw(img).rectangle((POWER.x, POWER.y, POWER.x + POWER.w, POWER.y + POWER.h), fill=(255, 128, 0))
    return img


def color_of(line):
    return "orange" if line is POWER else "blue"
