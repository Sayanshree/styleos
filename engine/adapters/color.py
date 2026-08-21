"""Colour normalisation for adapter output.

Colours are stored numerically as `{h, s, l}` jsonb — never as colour-name
strings. Colour-harmony scoring is arithmetic on these numbers, and string
matching is not a substitute for it.

The CV model is asked for a hex string, which converts to HSL exactly. The named
-colour table below is a fallback for when the model answers with a word anyway;
it is deliberately short, covering what actually turns up describing clothing.
"""

from __future__ import annotations

from typing import Final, TypedDict


class Hsl(TypedDict):
    """Hue 0-359, saturation 0-100, lightness 0-100."""

    h: int
    s: int
    l: int  # noqa: E741 - `l` is the stored jsonb key; the name is the data contract


def hsl_to_dict(value: Hsl) -> dict[str, int]:
    """Widen an Hsl TypedDict to a plain dict for jsonb storage.

    `dict(value)` would type as dict[str, object] and lose the int, which the
    repository signature needs.
    """
    return {"h": value["h"], "s": value["s"], "l": value["l"]}


#: Neutral mid-grey. Used when a colour cannot be determined at all — it is
#: deliberately unsaturated so it does not fake a colour preference the user
#: never expressed.
NEUTRAL_GREY: Final[Hsl] = {"h": 0, "s": 0, "l": 50}

NAMED_COLORS: Final[dict[str, str]] = {
    "black": "#000000",
    "white": "#ffffff",
    "grey": "#808080",
    "gray": "#808080",
    "charcoal": "#36454f",
    "silver": "#c0c0c0",
    "navy": "#000080",
    "blue": "#0000ff",
    "sky blue": "#87ceeb",
    "teal": "#008080",
    "turquoise": "#40e0d0",
    "green": "#008000",
    "olive": "#808000",
    "khaki": "#c3b091",
    "yellow": "#ffff00",
    "mustard": "#ffdb58",
    "orange": "#ffa500",
    "rust": "#b7410e",
    "red": "#ff0000",
    "burgundy": "#800020",
    "maroon": "#800000",
    "pink": "#ffc0cb",
    "purple": "#800080",
    "lavender": "#e6e6fa",
    "brown": "#a52a2a",
    "tan": "#d2b48c",
    "beige": "#f5f5dc",
    "cream": "#fffdd0",
    "ivory": "#fffff0",
    "denim": "#1560bd",
}


def rgb_to_hsl(red: float, green: float, blue: float) -> Hsl:
    """Convert RGB in the 0-1 range to integer HSL."""
    high = max(red, green, blue)
    low = min(red, green, blue)
    lightness = (high + low) / 2

    if high == low:
        # Achromatic: hue is undefined, so report 0 rather than an arbitrary value.
        return {"h": 0, "s": 0, "l": round(lightness * 100)}

    delta = high - low
    saturation = delta / (2 - high - low) if lightness > 0.5 else delta / (high + low)

    if high == red:
        hue = ((green - blue) / delta) % 6
    elif high == green:
        hue = (blue - red) / delta + 2
    else:
        hue = (red - green) / delta + 4

    return {
        "h": round(hue * 60) % 360,
        "s": round(saturation * 100),
        "l": round(lightness * 100),
    }


def hex_to_hsl(value: str) -> Hsl:
    """Convert `#rrggbb` or `#rgb` to HSL. Raises ValueError on anything else."""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    try:
        red = int(text[0:2], 16) / 255
        green = int(text[2:4], 16) / 255
        blue = int(text[4:6], 16) / 255
    except ValueError as exc:
        raise ValueError(f"not a hex colour: {value!r}") from exc
    return rgb_to_hsl(red, green, blue)


def to_hsl(value: str | None) -> Hsl:
    """Best-effort conversion of whatever the model returned into HSL.

    Tries hex first, then the named-colour table, then gives up and returns
    neutral grey. Never raises: a colour we cannot parse must not fail an upload.
    """
    if not value:
        return NEUTRAL_GREY

    candidate = value.strip().lower()
    try:
        return hex_to_hsl(candidate)
    except ValueError:
        pass

    mapped = NAMED_COLORS.get(candidate)
    if mapped is not None:
        return hex_to_hsl(mapped)

    return NEUTRAL_GREY
