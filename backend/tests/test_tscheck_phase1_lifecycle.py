import subprocess
import time
import uuid


def make_brief():
    return {
        "topic": f"tscheck-video-{uuid.uuid4().hex[:8]}",
        "audience": "हिंदी सीखने वाले युवा",
        "duration_seconds": 15,
        "tone": "विश्वसनीय",
        "cta": "आज ही शुरू करें",
        "style_guidance": "शांत और स्पष्ट",
        "must_include": ["तीन छोटे कदम"],
        "exclusions": [],
    }


def wait_job(client, job_id, statuses, timeout=45):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/jobs/{job_id}")
        assert last.status_code == 200, last.text
        job = last.json()
        if job["status"] in statuses:
            return job
        time.sleep(1)
    raise AssertionError(f"job did not reach {statuses}; last={last.text if last else None}")


def test_tscheck_job_script_voice_render_approval_persists(client, tmp_path):
    created = client.post("/jobs", json={"brief": make_brief()})
    assert created.status_code == 200, created.text
    job = created.json()
    job_id = job["id"]
    assert job["status"] == "queued"

    job = wait_job(client, job_id, {"voice_required"})
    assert job["script"] and any("क" <= char <= "ह" for char in job["script"])

    edited = job["script"] + " यह संपादित संदेश है।"
    saved = client.patch(f"/jobs/{job_id}/script", json={"script": edited})
    assert saved.status_code == 200, saved.text
    assert saved.json()["script"] == edited

    audio_path = tmp_path / "tscheck-valid.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:a", "pcm_s16le", str(audio_path)], check=True, capture_output=True)
    with audio_path.open("rb") as audio:
        uploaded = client.post(
            f"/jobs/{job_id}/voice",
            files={"file": ("tscheck-valid.wav", audio, "audio/wav")},
        )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "composing"
    assert 3 <= uploaded.json()["voice_duration"] <= 45

    ready = wait_job(client, job_id, {"ready_for_approval"}, timeout=120)
    assert ready["video_url"].endswith(".mp4")
    media = client.get(ready["video_url"].replace("/api", "", 1))
    assert media.status_code == 200
    assert media.headers["content-type"].split(";")[0] == "video/mp4"
    with open("/tmp/tscheck-render.mp4", "wb") as out:
        out.write(media.content)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "json", "/tmp/tscheck-render.mp4"],
        check=True, capture_output=True, text=True,
    )
    assert '"width": 1080' in probe.stdout and '"height": 1920' in probe.stdout

    events = client.get(f"/jobs/{job_id}/events")
    assert events.status_code == 200
    names = [event["event"] for event in events.json()]
    assert "queued" in names and "script_edited" in names and "composing" in names and "validating" in names
    before = len(events.json())
    approved = client.post(f"/jobs/{job_id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] is True and approved.json()["status"] == "approved"
    after_events = client.get(f"/jobs/{job_id}/events").json()
    assert len(after_events) == before + 1 and after_events[-1]["event"] == "approved"

    reloaded = client.get(f"/jobs/{job_id}")
    assert reloaded.status_code == 200
    assert reloaded.json()["id"] == job_id and reloaded.json()["approved"] is True
