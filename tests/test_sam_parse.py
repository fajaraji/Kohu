"""SAM output parsing against the documented example line."""

import sam_parse
from conftest import FIXTURES


def test_parse_documented_example_boxes():
    recs = sam_parse.parse((FIXTURES / "sam_two_records.txt").read_text())
    assert [r["object_id"] for r in recs] == ["0", "1"]
    assert recs[0]["box"] == {"x1": 211, "y1": 228, "x2": 271, "y2": 255}
    assert recs[0]["w"] == 320 and recs[0]["h"] == 334
    assert recs[0]["mask_data"].startswith("27,60,~")


def test_empty_output_is_no_match():
    assert sam_parse.parse("") == []
    assert sam_parse.best([]) is None


def test_box_prompt_format_and_clamp():
    assert sam_parse.box_prompt(10, 20, 39, 59, 640, 480) == \
        "<0f>1<|box;x1=10;y1=20;x2=39;y2=59;w=640;h=480|>"
    assert "x2=639" in sam_parse.box_prompt(0, 0, 9999, 10, 640, 480)


def test_render_mark_png(tmp_path):
    from PIL import Image
    recs = sam_parse.parse((FIXTURES / "sam_two_records.txt").read_text())
    kind = sam_parse.render_mark_png(recs[0], tmp_path / "m.png")
    img = Image.open(tmp_path / "m.png")
    assert img.size == (320, 334) and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0          # outside stays clear
    assert img.getpixel((240, 240))[3] > 0       # inside the box is marked
    assert kind == ("mask" if sam_parse.parser_available() else "box")


def _official(text):
    """Records from Meta's meta_sam_parser, for cross-checking ours."""
    import meta_sam_parser as msp
    p = msp.image_segmentation_format().create_parser()
    p.push(text)
    res = p.finish(msp.CompletedOutcome())
    res = getattr(res, "result", res)
    return [r for r in res.records if r.kind == "mask"], msp


def test_masks_match_meta_parser():
    """Boxes and every mask pixel agree with Meta's own parser, on the
    documented example and on a live SAM 3.1 output."""
    import pytest
    if not sam_parse.parser_available():
        pytest.skip("meta-sam-parser not installed")
    for name in ("sam_two_records.txt", "live_sam_mask.txt"):
        text = (FIXTURES / name).read_text()
        ours = sam_parse.parse(text)
        theirs, msp = _official(text)
        assert len(ours) == len(theirs) > 0
        for o, t in zip(ours, theirs):
            b = t.bounds
            assert (o["box"]["x1"], o["box"]["y1"], o["box"]["x2"],
                    o["box"]["y2"]) == (b.left, b.top, b.right, b.bottom)
            flat = bytes(v for row in o["mask"]["rows"] for v in row)
            assert flat == msp.decode_mask_to_raster(t.mask)
            assert 0 < sam_parse.mask_fraction(o) <= 1
