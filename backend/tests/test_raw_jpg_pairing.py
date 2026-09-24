import pytest
from pathlib import Path
from services.ingester import ImageRecord
from services.clustering import ImageCluster
from services.decision import apply_decision_logic
from services.xmp_exporter import export_results_to_xmp

def test_raw_jpg_decision_does_not_duplicate():
    record = ImageRecord(
        path="C:/photos/IMG_0001.JPG",
        filename="IMG_0001.JPG",
        is_raw=False,
        linked_raw_path="C:/photos/IMG_0001.CR2"
    )
    cluster = ImageCluster(cluster_id=0, image_indices=[0], scene_type="portrait")
    
    class FakeAnalysis:
        scene_type = "portrait"
        face_bboxes = []
        face_sharpness = []
        face_attrs = []
        blur_score = 100.0
        aesthetic_score = 0.8
        valid_face_count = 0
        closed_eyes_count = 0
        looking_away_count = 0
        smiling_count = 0

    results, demoted, final_selected, highlights = apply_decision_logic(
        records=[record],
        analyses=[FakeAnalysis()],
        clusters=[cluster],
        rep_scores={0: 0.9},
        all_scores={0: 0.9},
        gate_reasons={},
        decided_by={},
        margins={0: 1.0},
        trash_flags=[False],
        prefs={"selectivity_target": "standard"},
        settings={"ratings_mapping": {}},
        develop_by_idx={},
        exact_duplicates={},
        identities_map={},
        vip_photo_indices=set(),
        chapter_map={},
    )
    
    # Debe haber solo 1 resultado en la lista, no 2
    assert len(results) == 1
    assert results[0]["path"] == "C:/photos/IMG_0001.JPG"
    assert results[0]["linked_raw_path"] == "C:/photos/IMG_0001.CR2"

def test_xmp_export_writes_both_jpg_and_raw(tmp_path):
    jpg_path = tmp_path / "IMG_0001.JPG"
    raw_path = tmp_path / "IMG_0001.CR2"
    
    from PIL import Image
    img = Image.new("RGB", (10, 10), color="red")
    img.save(jpg_path)
    raw_path.write_bytes(b"dummy raw content")
    
    results = [{
        "path": str(jpg_path),
        "linked_raw_path": str(raw_path),
        "label": "selected",
        "stars": 3,
        "color": "Verde"
    }]
    ratings_map = {"selected": {"stars": 3, "color": "Verde"}}
    
    export_results_to_xmp(results, ratings_map, overwrite=True)
    
    xmp_raw = tmp_path / "IMG_0001.xmp"
    assert xmp_raw.exists()
    content = xmp_raw.read_text(encoding="utf-8")
    assert "<xmp:Rating>3</xmp:Rating>" in content
    assert "<xmp:Label>Verde</xmp:Label>" in content
