import json
import pytest
from core.job_manager import JobManager
from fastapi.testclient import TestClient
from main import app


def test_job_manager_pub_sub():
    jm = JobManager()
    q1 = jm.subscribe()
    
    # Snapshot inicial
    initial = q1.get_nowait()
    assert initial["type"] == "snapshot"
    assert initial["data"]["status"] == "idle"

    # Emitir evento
    jm.update_progress(processed=5, total=10, progress=50.0, phase_text="Analizando...")
    event = q1.get_nowait()
    assert event["type"] == "progress"
    assert event["data"]["processed"] == 5
    assert event["data"]["progress"] == 50.0

    jm.unsubscribe(q1)
    jm.set_phase("Fase final")
    # Ya no debe recibir eventos tras desuscribirse
    assert q1.empty()


@pytest.mark.anyio
async def test_sse_endpoint_generator():
    from routers.culling import stream_events
    response = await stream_events()
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"

    gen = response.body_iterator
    first_chunk = await anext(gen)
    assert first_chunk.startswith("data: ")
    payload = json.loads(first_chunk[len("data: "):])
    assert payload["type"] == "snapshot"
    await gen.aclose()

