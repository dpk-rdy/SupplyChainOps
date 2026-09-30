"""Chart palette for the local dashboard render.

Values come from a validated, colorblind-safe reference palette (light surface #fcfcfb).
Categorical hues are assigned in fixed order to fixed entities (macro-regions), never cycled.
"""

SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# Fixed entity -> hue mapping so a filter never repaints the survivors.
MACRO_REGION_COLORS = {
    "Sudeste": CATEGORICAL[0],
    "Sul": CATEGORICAL[1],
    "Nordeste": CATEGORICAL[2],
    "Centro-Oeste": CATEGORICAL[3],
    "Norte": CATEGORICAL[4],
}

SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
FORECAST_BAND = "rgba(42, 120, 214, 0.18)"
