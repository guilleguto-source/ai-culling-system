"""
test_metadata_manager.py — Tests para gestión de perfiles de copyright, tags de eventos y XMP.
"""
import tempfile
from pathlib import Path
from lxml import etree
import pytest

from services.metadata_manager import (
    get_metadata_profiles,
    save_or_update_profile,
    delete_metadata_profile,
    set_default_profile,
    build_batch_metadata_payload,
    detect_gps_in_directory,
    EVENT_TAXONOMY,
)
from services.xmp_exporter import update_file_metadata, write_xmp, NS


def test_build_batch_metadata_payload_dynamics():
    profile = {
        "creator": "Guille Guto",
        "copyright_notice": "© {year} {creator}. Derechos de {client}.",
        "credit": "Guto Studios",
        "usage_terms": "Solo uso personal",
        "web_statement": "https://guilleguto.com"
    }

    payload = build_batch_metadata_payload(
        profile=profile,
        event_type="matine",
        age="5",
        protagonist="Santi",
        city="Samborondón",
        custom_tags_str="Decoración, Payaso, Torta",
        year=2026
    )

    assert payload["creator"] == "Guille Guto"
    assert payload["copyright"] == "© 2026 Guille Guto. Derechos de Santi."
    assert payload["city"] == "Samborondón"
    assert payload["country"] == "Ecuador"
    assert payload["title"] == "Santi"

    # Verificar que los tags consolidados incluyan base, edad, protagonista, ciudad y custom
    tags = payload["keywords"]
    assert "Matiné" in tags
    assert "Infantil" in tags
    assert "5 Años" in tags
    assert "Santi" in tags
    assert "Samborondón" in tags
    assert "Decoración" in tags
    assert "Payaso" in tags
    assert "Torta" in tags


def test_profile_crud(tmp_path, monkeypatch):
    test_file = tmp_path / "test_profiles.json"
    monkeypatch.setattr("services.metadata_manager._get_profiles_path", lambda: test_file)

    # 1. Obtener perfiles por defecto
    profiles = get_metadata_profiles()
    assert len(profiles) >= 1
    default_p = profiles[0]
    assert default_p.get("is_default") is True

    # 2. Crear nuevo perfil
    new_p = {
        "name": "Boda Especial",
        "creator": "Fotógrafo 2",
        "copyright_notice": "© {year} Fotógrafo 2",
        "is_default": False
    }
    saved = save_or_update_profile(new_p)
    assert saved["id"] is not None

    profiles_after = get_metadata_profiles()
    assert len(profiles_after) == len(profiles) + 1

    # 3. Establecer como default
    set_default_profile(saved["id"])
    profiles_after_def = get_metadata_profiles()
    assert any(p["id"] == saved["id"] and p["is_default"] for p in profiles_after_def)

    # 4. Eliminar perfil
    deleted = delete_metadata_profile(saved["id"])
    assert deleted is True
    assert len(get_metadata_profiles()) == len(profiles)


def test_update_file_metadata_preserves_rating(tmp_path):
    # Crear un archivo RAW ficticio con sidecar .xmp con 5 estrellas y etiqueta Verde
    raw_path = tmp_path / "DSC_1001.ARW"
    raw_path.write_bytes(b"FAKE_RAW_DATA")

    # Escribir rating previo con write_xmp
    write_xmp(
        image_path=str(raw_path),
        label="selected",
        stars=5,
        color="Green",
        flag="pick",
        overwrite=True
    )

    sidecar = raw_path.with_suffix(".xmp")
    assert sidecar.exists()

    # Comprobar que inicialmente tiene rating 5
    tree_before = etree.parse(str(sidecar))
    rating_el = tree_before.find(f".//{{{NS['xmp']}}}Rating")
    assert rating_el is not None
    assert rating_el.text == "5"

    label_el = tree_before.find(f".//{{{NS['xmp']}}}Label")
    assert label_el is not None
    assert label_el.text == "Green"

    # Ahora aplicar metadatos (Copyright, Autor, Keywords, Ciudad)
    meta = {
        "creator": "Guille Guto",
        "copyright": "© 2026 Guille Guto. All rights reserved.",
        "credit": "Guille Guto Studio",
        "title": "Boda Carlos & Sofia",
        "city": "Guayaquil",
        "country": "Ecuador",
        "keywords": ["Boda", "Matrimonio", "Guayaquil"]
    }

    ok = update_file_metadata(str(raw_path), meta, keywords_mode="append", update_dual_partner=False)
    assert ok is True

    # Verificar que el XMP contiene los nuevos metadatos y MANTIENE las 5 estrellas y etiqueta Verde
    tree_after = etree.parse(str(sidecar))
    
    # 1. Rating y Label preservados
    assert tree_after.find(f".//{{{NS['xmp']}}}Rating").text == "5"
    assert tree_after.find(f".//{{{NS['xmp']}}}Label").text == "Green"
    assert tree_after.find(f".//{{{NS['crs']}}}Pick").text == "1"

    # 2. Creator inyectado
    creator_el = tree_after.find(f".//{{{NS['dc']}}}creator")
    assert creator_el is not None
    assert creator_el.find(f".//{{{NS['rdf']}}}li").text == "Guille Guto"

    # 3. Rights inyectado
    rights_el = tree_after.find(f".//{{{NS['dc']}}}rights")
    assert rights_el is not None
    assert rights_el.find(f".//{{{NS['rdf']}}}li").text == "© 2026 Guille Guto. All rights reserved."

    # 4. Ciudad inyectada
    city_el = tree_after.find(f".//{{{NS['photoshop']}}}City")
    assert city_el is not None
    assert city_el.text == "Guayaquil"

    # 5. Keywords inyectadas
    subj_el = tree_after.find(f".//{{{NS['dc']}}}subject")
    assert subj_el is not None
    tags = [li.text for li in subj_el.findall(f".//{{{NS['rdf']}}}li")]
    assert "Boda" in tags
    assert "Matrimonio" in tags
    assert "Guayaquil" in tags

    # Probar ahora keywords_mode="append" con tags nuevos
    meta2 = {
        "keywords": ["Recepción", "Boda"]  # Boda ya existe, no debe duplicarse
    }
    update_file_metadata(str(raw_path), meta2, keywords_mode="append", update_dual_partner=False)

    tree_after_append = etree.parse(str(sidecar))
    subj_el2 = tree_after_append.find(f".//{{{NS['dc']}}}subject")
    tags2 = [li.text for li in subj_el2.findall(f".//{{{NS['rdf']}}}li")]
    assert "Recepción" in tags2
    assert tags2.count("Boda") == 1  # No duplicado


def test_detect_gps_empty_dir(tmp_path):
    res = detect_gps_in_directory(str(tmp_path))
    assert res["has_gps"] is False
    assert res["latitude"] is None
