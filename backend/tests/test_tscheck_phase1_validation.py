import uuid


def test_tscheck_rejects_invalid_brief_and_audio(client):
    invalid_brief = client.post(
        "/jobs",
        json={"brief": {"topic": "", "audience": "x", "duration_seconds": 20}},
    )
    assert invalid_brief.status_code == 422, invalid_brief.text

    valid = client.post(
        "/jobs",
        json={
            "brief": {
                "topic": f"tscheck-invalid-audio-{uuid.uuid4().hex[:8]}",
                "audience": "युवा",
                "duration_seconds": 15,
            }
        },
    )
    assert valid.status_code == 200, valid.text
    job_id = valid.json()["id"]
    invalid_audio = client.post(
        f"/jobs/{job_id}/voice",
        files={"file": ("not-audio.txt", b"not audio", "text/plain")},
    )
    assert invalid_audio.status_code == 415, invalid_audio.text
