from gazescope.core.demo import create_demo_session
from gazescope.core.report import export_html
from gazescope.core.session import AOI, Session, list_sessions


def test_demo_session_roundtrip(tmp_path):
    path = create_demo_session(tmp_path)
    assert (path / "thumb.jpg").exists()
    assert [p for p, _ in list_sessions(tmp_path)] == [path]

    s = Session(path)
    assert len(s.scenes) == 2
    assert s.fixations and all(f.scene_id in (0, 1) for f in s.fixations)
    m = s.metrics(0)
    assert m["fixations"] > 5 and 0 < m["coverage"] < 1

    stats = {a["name"]: a for a in s.aoi_stats(0)}
    assert stats["Botón CTA"]["fixations"] >= 2
    assert stats["Botón CTA"]["revisits"] >= 1

    s.aois[1] = [AOI("Precio", 990, 330, 400, 100)]
    s.save_aois()
    assert Session(path).aois[1][0].name == "Precio"

    # Recalcular fijaciones desde las muestras crudas debe dar un resultado similar.
    before = len(s.fixations)
    s.recompute_fixations(45.0, 100.0, 1.5, 75.0)
    assert abs(len(s.fixations) - before) <= 2

    html = export_html(s, path / "report.html").read_text(encoding="utf-8")
    assert "data:image/jpeg;base64," in html and "Botón CTA" in html
