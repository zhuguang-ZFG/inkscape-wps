from inkscape_wps.core.config import MachineConfig
from inkscape_wps.ui.stroke_layout import StrokeLayoutEngine


def test_layout_wrap_and_lines():
    eng = StrokeLayoutEngine(font_px=16, line_spacing=1.4)
    rows = eng.layout("abcdefg", viewport_width=60, margin_px=10)
    assert len(rows) >= 2
    assert rows[0].text


def test_to_layout_lines_not_empty():
    eng = StrokeLayoutEngine(font_px=16, line_spacing=1.4)
    rows = eng.layout("abc\ndef", viewport_width=220, margin_px=10)
    cfg = MachineConfig()
    lines = eng.to_layout_lines(rows, cfg, viewport_width_px=220, viewport_height_px=200)
    assert len(lines) >= 2


def test_empty_lines_use_default_row_height():
    eng = StrokeLayoutEngine(font_px=16, line_spacing=1.45)
    _, _, default_h = eng._default_vertical()
    rows = eng.layout("\n\n", viewport_width=220, margin_px=10)
    assert len(rows) >= 2
    for r in rows:
        if not r.text:
            assert r.h_px == default_h
            assert r.baseline_du == r.ascent_du


def test_line_spacing_scales_leading():
    lo = StrokeLayoutEngine(font_px=20, line_spacing=1.0)
    hi = StrokeLayoutEngine(font_px=20, line_spacing=2.0)
    assert hi._leading_du() > lo._leading_du()
