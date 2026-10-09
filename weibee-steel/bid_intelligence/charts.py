"""Small inline-SVG chart helpers for the report. No JavaScript libraries: the report is one file
that opens anywhere, and every mark carries a native tooltip (<title>) plus a table view.

Palette values come from a validated colour-blind-safe reference palette; categorical hues are
assigned to fixed entities (estimate = blue, actual = orange, backlog = blue, pipeline = amber).
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence

BLUE, ORANGE, GREEN, AMBER, PINK, PURPLE = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
FONT = "font-family='Inter, system-ui, sans-serif'"


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def fmt_pct(v: float, digits: int = 0) -> str:
    return "–" if v is None or v != v else f"{v * 100:.{digits}f}%"


def fmt_money(v: float) -> str:
    if v is None or v != v:
        return "–"
    a = abs(v)
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    if a >= 1e3:
        return f"${v / 1e3:.0f}k"
    return f"${v:.0f}"


def fmt_int(v: float) -> str:
    return "–" if v is None or v != v else f"{v:,.0f}"


def fmt_pts(v: float) -> str:
    return "–" if v is None or v != v else f"{v * 100:+.1f} pts"


# ------------------------------------------------------------------ horizontal bars
def hbar(
    rows: Sequence[dict],
    value_fmt: Callable[[float], str] = fmt_pct,
    max_value: float | None = None,
    color: str = BLUE,
    width: int = 640,
    bar_h: int = 20,
    label_w: int = 190,
    reference: float | None = None,
    reference_label: str = "",
) -> str:
    """rows: {label, value, note?, tooltip?, color?}. Bars grow from a shared baseline."""
    if not rows:
        return "<p class='muted'>No data.</p>"
    vmax = max_value or max(r["value"] for r in rows) or 1.0
    plot_w = width - label_w - 90
    h = len(rows) * (bar_h + 8) + 12
    out = [f"<svg viewBox='0 0 {width} {h}' width='100%' role='img' {FONT} font-size='12'>"]
    if reference is not None:
        x = label_w + plot_w * reference / vmax
        out.append(
            f"<line x1='{x:.1f}' x2='{x:.1f}' y1='4' y2='{h - 6}' stroke='var(--ink-muted)' stroke-dasharray='3 3'/>"
        )
        out.append(
            f"<text x='{x + 4:.1f}' y='{h - 2}' fill='var(--ink-muted)' font-size='10'>{_esc(reference_label)}</text>"
        )
    for i, r in enumerate(rows):
        y = 6 + i * (bar_h + 8)
        w = max(0.0, plot_w * r["value"] / vmax)
        tip = r.get("tooltip") or f"{r['label']}: {value_fmt(r['value'])}"
        c = r.get("color", color)
        out.append("<g>")
        out.append(f"<title>{_esc(tip)}</title>")
        out.append(
            f"<text x='{label_w - 8}' y='{y + bar_h * 0.72:.1f}' text-anchor='end' fill='var(--ink-2)'>{_esc(r['label'])}</text>"
        )
        out.append(f"<rect x='{label_w}' y='{y}' width='{w:.1f}' height='{bar_h}' rx='3' fill='{c}'/>")
        note = f" <tspan fill='var(--ink-muted)'>{_esc(r['note'])}</tspan>" if r.get("note") else ""
        out.append(
            f"<text x='{label_w + w + 6:.1f}' y='{y + bar_h * 0.72:.1f}' fill='var(--ink)'>{value_fmt(r['value'])}{note}</text>"
        )
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ dumbbell (estimate vs actual)
def dumbbell(
    rows: Sequence[dict],
    x_min: float,
    x_max: float,
    fmt: Callable[[float], str] = fmt_pct,
    a_label: str = "Estimated",
    b_label: str = "Actual",
    width: int = 640,
    row_h: int = 26,
    label_w: int = 190,
) -> str:
    """rows: {label, a, b, note?}. Draws a-dot (blue) and b-dot (orange) joined by a line."""
    if not rows:
        return "<p class='muted'>No completed jobs yet.</p>"
    plot_w = width - label_w - 80
    h = len(rows) * row_h + 34

    def sx(v: float) -> float:
        return label_w + plot_w * (v - x_min) / (x_max - x_min)

    out = [f"<svg viewBox='0 0 {width} {h}' width='100%' role='img' {FONT} font-size='12'>"]
    for t in _ticks(x_min, x_max, 5):
        out.append(f"<line x1='{sx(t):.1f}' x2='{sx(t):.1f}' y1='6' y2='{h - 26}' stroke='var(--grid)'/>")
        out.append(
            f"<text x='{sx(t):.1f}' y='{h - 12}' text-anchor='middle' fill='var(--ink-muted)' font-size='10'>{fmt(t)}</text>"
        )
    for i, r in enumerate(rows):
        y = 16 + i * row_h
        xa, xb = sx(r["a"]), sx(r["b"])
        tip = f"{r['label']}: {a_label} {fmt(r['a'])}, {b_label} {fmt(r['b'])}" + (
            f" ({r['note']})" if r.get("note") else ""
        )
        out.append(f"<g><title>{_esc(tip)}</title>")
        out.append(
            f"<text x='{label_w - 8}' y='{y + 4}' text-anchor='end' fill='var(--ink-2)'>{_esc(r['label'])}</text>"
        )
        out.append(
            f"<line x1='{xa:.1f}' x2='{xb:.1f}' y1='{y}' y2='{y}' stroke='var(--ink-muted)' stroke-width='2'/>"
        )
        out.append(
            f"<circle cx='{xa:.1f}' cy='{y}' r='5' fill='{BLUE}' stroke='var(--surface)' stroke-width='2'/>"
        )
        out.append(
            f"<circle cx='{xb:.1f}' cy='{y}' r='5' fill='{ORANGE}' stroke='var(--surface)' stroke-width='2'/>"
        )
        out.append(
            f"<text x='{max(xa, xb) + 10:.1f}' y='{y + 4}' fill='var(--ink)' font-size='11'>{fmt_pts(r['b'] - r['a'])}"
            + (f" <tspan fill='var(--ink-muted)'>{_esc(r['note'])}</tspan>" if r.get("note") else "")
            + "</text>"
        )
        out.append("</g>")
    out.append("</svg>")
    out.append(legend([(a_label, BLUE), (b_label, ORANGE)]))
    return "".join(out)


# ------------------------------------------------------------------ vertical bars (histogram)
def vbar(
    categories: Sequence[str],
    values: Sequence[float],
    color: str = BLUE,
    fmt: Callable[[float], str] = fmt_int,
    width: int = 640,
    height: int = 220,
) -> str:
    if not categories:
        return "<p class='muted'>No data.</p>"
    vmax = max(values) or 1.0
    left, bottom, top = 36, 34, 14
    plot_w, plot_h = width - left - 10, height - bottom - top
    n = len(categories)
    slot = plot_w / n
    bw = slot * 0.72
    out = [f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' {FONT} font-size='12'>"]
    for t in _ticks(0, vmax, 4):
        y = top + plot_h - plot_h * t / vmax
        out.append(f"<line x1='{left}' x2='{width - 10}' y1='{y:.1f}' y2='{y:.1f}' stroke='var(--grid)'/>")
        out.append(
            f"<text x='{left - 6}' y='{y + 4:.1f}' text-anchor='end' fill='var(--ink-muted)' font-size='10'>{fmt(t)}</text>"
        )
    for i, (c, v) in enumerate(zip(categories, values, strict=True)):
        x = left + i * slot + (slot - bw) / 2
        bh = plot_h * v / vmax
        y = top + plot_h - bh
        out.append(f"<g><title>{_esc(c)}: {fmt(v)}</title>")
        out.append(
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{bh:.1f}' rx='3' fill='{color}'/>"
        )
        out.append(
            f"<text x='{x + bw / 2:.1f}' y='{y - 4:.1f}' text-anchor='middle' fill='var(--ink)' font-size='11'>{fmt(v)}</text>"
        )
        out.append(
            f"<text x='{x + bw / 2:.1f}' y='{height - 14}' text-anchor='middle' fill='var(--ink-2)' font-size='11'>{_esc(c)}</text>"
        )
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ lines over time
def line_chart(
    x_labels: Sequence[str],
    series: Sequence[tuple[str, str, Sequence[float]]],
    y_fmt: Callable[[float], str] = fmt_pct,
    y_max: float | None = None,
    width: int = 640,
    height: int = 240,
    tooltips: Sequence[str] | None = None,
) -> str:
    """series: (name, color, values aligned with x_labels). One y-axis; crosshair tooltip per x."""
    if not x_labels:
        return "<p class='muted'>No data.</p>"
    vmax = y_max or max(v for _, _, vals in series for v in vals if v == v) * 1.1 or 1.0
    left, bottom, top, right = 44, 30, 12, 12
    plot_w, plot_h = width - left - right, height - bottom - top
    n = len(x_labels)

    def sx(i: int) -> float:
        return left + (plot_w * i / max(n - 1, 1))

    def sy(v: float) -> float:
        return top + plot_h - plot_h * v / vmax

    out = [f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' {FONT} font-size='12'>"]
    for t in _ticks(0, vmax, 4):
        out.append(
            f"<line x1='{left}' x2='{width - right}' y1='{sy(t):.1f}' y2='{sy(t):.1f}' stroke='var(--grid)'/>"
        )
        out.append(
            f"<text x='{left - 6}' y='{sy(t) + 4:.1f}' text-anchor='end' fill='var(--ink-muted)' font-size='10'>{y_fmt(t)}</text>"
        )
    step = max(1, n // 8)
    for i, lab in enumerate(x_labels):
        if i % step == 0 or i == n - 1:
            out.append(
                f"<text x='{sx(i):.1f}' y='{height - 10}' text-anchor='middle' fill='var(--ink-muted)' font-size='10'>{_esc(lab)}</text>"
            )
    for _name, color, vals in series:
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals) if v == v)
        out.append(
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2' stroke-linejoin='round'/>"
        )
        last = [(i, v) for i, v in enumerate(vals) if v == v]
        if last:
            i, v = last[-1]
            out.append(
                f"<circle cx='{sx(i):.1f}' cy='{sy(v):.1f}' r='4' fill='{color}' stroke='var(--surface)' stroke-width='2'/>"
            )
    slot = plot_w / max(n - 1, 1)
    for i, lab in enumerate(x_labels):
        tip = (
            tooltips[i]
            if tooltips
            else f"{lab}: " + ", ".join(f"{nm} {y_fmt(vals[i])}" for nm, _, vals in series)
        )
        out.append(
            f"<rect x='{sx(i) - slot / 2:.1f}' y='{top}' width='{slot:.1f}' height='{plot_h}' fill='transparent'><title>{_esc(tip)}</title></rect>"
        )
    out.append("</svg>")
    out.append(legend([(nm, c) for nm, c, _ in series]))
    return "".join(out)


def stacked_area(
    x_labels: Sequence[str],
    layers: Sequence[tuple[str, str, Sequence[float]]],
    line: tuple[str, str, Sequence[float]] | None = None,
    y_fmt: Callable[[float], str] = fmt_int,
    width: int = 640,
    height: int = 260,
    today_index: int | None = None,
) -> str:
    """Stacked areas (e.g. backlog + weighted pipeline) under a reference line (capacity)."""
    n = len(x_labels)
    if n == 0:
        return "<p class='muted'>No data.</p>"
    totals = [sum(layer[2][i] for layer in layers) for i in range(n)]
    vmax = max(max(totals), max(line[2]) if line else 0) * 1.15 or 1.0
    left, bottom, top, right = 44, 30, 12, 12
    plot_w, plot_h = width - left - right, height - bottom - top

    def sx(i: int) -> float:
        return left + plot_w * i / max(n - 1, 1)

    def sy(v: float) -> float:
        return top + plot_h - plot_h * v / vmax

    out = [f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' {FONT} font-size='12'>"]
    for t in _ticks(0, vmax, 4):
        out.append(
            f"<line x1='{left}' x2='{width - right}' y1='{sy(t):.1f}' y2='{sy(t):.1f}' stroke='var(--grid)'/>"
        )
        out.append(
            f"<text x='{left - 6}' y='{sy(t) + 4:.1f}' text-anchor='end' fill='var(--ink-muted)' font-size='10'>{y_fmt(t)}</text>"
        )
    base = [0.0] * n
    for _name, color, vals in layers:
        upper = [base[i] + vals[i] for i in range(n)]
        top_pts = " ".join(f"{sx(i):.1f},{sy(upper[i]):.1f}" for i in range(n))
        bot_pts = " ".join(f"{sx(i):.1f},{sy(base[i]):.1f}" for i in reversed(range(n)))
        out.append(
            f"<polygon points='{top_pts} {bot_pts}' fill='{color}' fill-opacity='0.55' stroke='{color}' stroke-width='1.5'/>"
        )
        base = upper
    if line:
        name, color, vals = line
        pts = " ".join(f"{sx(i):.1f},{sy(vals[i]):.1f}" for i in range(n))
        out.append(
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2' stroke-dasharray='6 4'/>"
        )
    if today_index is not None:
        out.append(
            f"<line x1='{sx(today_index):.1f}' x2='{sx(today_index):.1f}' y1='{top}' y2='{top + plot_h}' stroke='var(--ink-muted)' stroke-dasharray='2 3'/>"
        )
        out.append(
            f"<text x='{sx(today_index) + 4:.1f}' y='{top + 12}' fill='var(--ink-muted)' font-size='10'>today</text>"
        )
    step = max(1, n // 8)
    for i, lab in enumerate(x_labels):
        if i % step == 0 or i == n - 1:
            out.append(
                f"<text x='{sx(i):.1f}' y='{height - 10}' text-anchor='middle' fill='var(--ink-muted)' font-size='10'>{_esc(lab)}</text>"
            )
    slot = plot_w / max(n - 1, 1)
    for i, lab in enumerate(x_labels):
        parts = [f"{nm} {y_fmt(vals[i])}" for nm, _, vals in layers]
        if line:
            parts.append(f"{line[0]} {y_fmt(line[2][i])}")
        out.append(
            f"<rect x='{sx(i) - slot / 2:.1f}' y='{top}' width='{slot:.1f}' height='{plot_h}' fill='transparent'><title>{_esc(lab + ': ' + ', '.join(parts))}</title></rect>"
        )
    out.append("</svg>")
    items = [(nm, c) for nm, c, _ in layers] + ([(line[0], line[1])] if line else [])
    out.append(legend(items))
    return "".join(out)


def calibration(rows: Sequence[dict], width: int = 300, height: int = 220) -> str:
    left, bottom, top, right = 40, 30, 10, 10
    pw, ph = width - left - right, height - bottom - top
    vmax = max([0.6] + [max(r["predicted"], r["observed"]) for r in rows]) * 1.05

    def sx(v: float) -> float:
        return left + pw * v / vmax

    def sy(v: float) -> float:
        return top + ph - ph * v / vmax

    out = [f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' {FONT} font-size='11'>"]
    for t in _ticks(0, vmax, 3):
        out.append(
            f"<line x1='{left}' x2='{width - right}' y1='{sy(t):.1f}' y2='{sy(t):.1f}' stroke='var(--grid)'/>"
        )
        out.append(
            f"<text x='{left - 5}' y='{sy(t) + 4:.1f}' text-anchor='end' fill='var(--ink-muted)' font-size='10'>{fmt_pct(t)}</text>"
        )
        out.append(
            f"<text x='{sx(t):.1f}' y='{height - 12}' text-anchor='middle' fill='var(--ink-muted)' font-size='10'>{fmt_pct(t)}</text>"
        )
    out.append(
        f"<line x1='{sx(0):.1f}' y1='{sy(0):.1f}' x2='{sx(vmax):.1f}' y2='{sy(vmax):.1f}' stroke='var(--ink-muted)' stroke-dasharray='3 3'/>"
    )
    pts = " ".join(f"{sx(r['predicted']):.1f},{sy(r['observed']):.1f}" for r in rows)
    out.append(f"<polyline points='{pts}' fill='none' stroke='{BLUE}' stroke-width='2'/>")
    for r in rows:
        out.append(
            f"<circle cx='{sx(r['predicted']):.1f}' cy='{sy(r['observed']):.1f}' r='5' fill='{BLUE}' stroke='var(--surface)' stroke-width='2'><title>bin {r['bin']}: predicted {fmt_pct(r['predicted'])}, observed {fmt_pct(r['observed'])} (n={r['bids']})</title></circle>"
        )
    out.append(
        f"<text x='{left + pw / 2:.1f}' y='{height - 1}' text-anchor='middle' fill='var(--ink-muted)' font-size='10'>predicted win probability</text>"
    )
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ helpers
def legend(items: Sequence[tuple[str, str]]) -> str:
    return (
        "<div class='legend'>"
        + "".join(f"<span><i style='background:{c}'></i>{_esc(n)}</span>" for n, c in items)
        + "</div>"
    )


def _ticks(lo: float, hi: float, n: int) -> list[float]:
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** int(f"{raw:e}".split("e")[1])
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    t, out = lo, []
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out
