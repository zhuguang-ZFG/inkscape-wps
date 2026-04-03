from inkscape_wps.ui.stroke_text_model import StrokeTextModel


def test_insert_delete_undo_redo():
    m = StrokeTextModel("abc")
    m.move_caret(3)
    m.insert_text("d")
    assert m.text == "abcd"
    m.backspace()
    assert m.text == "abc"
    assert m.undo() is True
    assert m.text == "abcd"
    assert m.redo() is True
    assert m.text == "abc"


def test_selection_replace():
    m = StrokeTextModel("hello world")
    m.move_caret(6)
    m.move_caret(11, keep_selection=True)
    m.replace_selection("wps")
    assert m.text == "hello wps"
