import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import zipfile
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
from lib.db import client, db, ensure_indexes

MEDIA_DIR = ROOT_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

class Brief(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    audience: str = Field(min_length=2, max_length=120)
    duration_seconds: int = Field(default=20, ge=15, le=30)
    tone: str = Field(default="विश्वसनीय", max_length=80)
    cta: str = Field(default="आज ही शुरू करें", max_length=160)
    style_guidance: str = Field(default="", max_length=500)
    must_include: list[str] = Field(default_factory=list, max_length=8)
    exclusions: list[str] = Field(default_factory=list, max_length=8)

class JobCreate(BaseModel):
    brief: Brief

class ScriptUpdate(BaseModel):
    script: str = Field(min_length=20, max_length=2500)

class Job(BaseModel):
    id: str
    status: str
    brief: Brief
    script: str = ""
    caption: str = ""
    voice_filename: str | None = None
    voice_duration: float | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    created_at: str
    updated_at: str
    fix_count: int = 0
    approved: bool = False
    error: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index_task = asyncio.create_task(ensure_indexes())
    yield
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()

app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")

async def add_event(job_id: str, event: str, detail: str = "") -> None:
    await db.job_events.insert_one({"id": str(uuid.uuid4()), "job_id": job_id, "event": event, "detail": detail, "created_at": now()})

async def update_job(job_id: str, status: str, **fields: Any) -> None:
    fields.update({"status": status, "updated_at": now()})
    await db.video_jobs.update_one({"id": job_id}, {"$set": fields})
    await add_event(job_id, status, fields.get("error", ""))

def fallback_script(brief: Brief) -> str:
    points = " ".join(brief.must_include) or "आसान कदम और भरोसेमंद नतीजे"
    return f"क्या आप {brief.audience} के लिए {brief.topic} को आसान बनाना चाहते हैं? {points} को सही तरीके से अपनाइए। {brief.style_guidance or 'छोटे, साफ़ और असरदार कदमों से शुरुआत करें'}। आज एक कदम उठाइए — {brief.cta}!"

async def generate_script(brief: Brief) -> str:
    prompt = json.dumps({"topic": brief.topic, "audience": brief.audience, "duration_seconds": brief.duration_seconds, "tone": brief.tone, "cta": brief.cta, "must_include": brief.must_include, "exclusions": brief.exclusions}, ensure_ascii=False)
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return fallback_script(brief)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta
        chat = LlmChat(api_key=key, session_id=f"video-{uuid.uuid4()}", system_message="You write concise natural Hindi Devanagari scripts for short vertical Reels. Return only the spoken script, no markdown, no headings, no invented claims.").with_model("openai", "gpt-5.4-mini")
        chunks: list[str] = []
        async for event in chat.stream_message(UserMessage(text=f"Write a {brief.duration_seconds}-second Hindi script for this brief: {prompt}")):
            if isinstance(event, TextDelta):
                chunks.append(event.content)
        result = "".join(chunks).strip()
        return result if result else fallback_script(brief)
    except Exception as exc:
        logger.warning("LLM generation failed, using contract-safe fallback: %s", exc)
        return fallback_script(brief)

def render_video(job_id: str, script: str, duration: int, audio_path: Path | None) -> tuple[Path, Path]:
    out = MEDIA_DIR / f"{job_id}.mp4"
    thumb = MEDIA_DIR / f"{job_id}.jpg"
    font = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
    safe = re.sub(r"[^\u0900-\u097F\w\s.,!?-]", "", script).replace(":", "\\:").replace("'", "\\'")[:170]
    # Offline composition: gradient-like solid panels, geometric accents, Devanagari text, and audio.
    vf = f"drawbox=x=0:y=0:w=iw:h=ih:color=0x101827:t=fill,drawbox=x=70:y=155:w=940:h=10:color=0xE7B75A:t=fill,drawbox=x=720:y=420:w=230:h=230:color=0x164E63@0.8:t=fill,drawtext=fontfile={font}:text='{safe}':fontcolor=white:fontsize=54:line_spacing=18:x=70:y=560:enable='between(t,0,{duration})',drawtext=fontfile={font}:text='VIDEO AGENT / PHASE 1':fontcolor=0xE7B75A:fontsize=25:x=70:y=120"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0b1220:s=1080x1920:r=30:d={duration}"]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    cmd += ["-vf", vf, "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30"]
    if audio_path:
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(thumb)], check=True, capture_output=True, timeout=30)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate,codec_name", "-of", "json", str(out)], check=True, capture_output=True, text=True)
    data = json.loads(probe.stdout)
    streams = data.get("streams", [])
    if not streams or streams[0].get("width") != 1080 or streams[0].get("height") != 1920:
        raise RuntimeError("render validation failed: expected 1080x1920")
    return out, thumb

async def process_job(job_id: str) -> None:
    row = await db.video_jobs.find_one({"id": job_id}, {"_id": 0})
    if not row:
        return
    try:
        await update_job(job_id, "scripting")
        script = await generate_script(Brief(**row["brief"]))
        await update_job(job_id, "voice_required", script=script, caption=script[:220])
    except Exception as exc:
        await update_job(job_id, "failed", error=str(exc))

@api_router.get("/")
async def root():
    return {"service": "video-agent", "phase": 1, "status": "ready"}

@api_router.get("/health")
async def health():
    return {"status": "ok", "renderer": "ffmpeg", "phase": 1}

@api_router.get("/project/download")
async def download_project():
    export = tempfile.NamedTemporaryFile(prefix="video-agent-project-", suffix=".zip", delete=False)
    export.close()
    root = ROOT_DIR.parent
    excluded = {".git", "node_modules", "__pycache__", ".pytest_cache", ".emergent", "media"}
    with zipfile.ZipFile(export.name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part in excluded for part in relative.parts):
                continue
            if path.name in {".env", ".env.local"} or path.suffix in {".mp4", ".wav", ".mp3", ".webm"}:
                continue
            archive.write(path, relative.as_posix())
    return FileResponse(export.name, media_type="application/zip", filename="video-agent-platform.zip")

@api_router.post("/jobs", response_model=Job)
async def create_job(body: JobCreate, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    stamp = now()
    doc = {"id": job_id, "status": "queued", "brief": body.brief.model_dump(), "script": "", "caption": "", "created_at": stamp, "updated_at": stamp, "fix_count": 0, "approved": False}
    await db.video_jobs.insert_one(doc)
    await add_event(job_id, "queued", "Brief accepted by the specification contract")
    background_tasks.add_task(process_job, job_id)
    return Job(**doc)

@api_router.get("/jobs", response_model=list[Job])
async def list_jobs():
    rows = await db.video_jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return [Job(**row) for row in rows]

@api_router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str):
    row = await db.video_jobs.find_one({"id": job_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Job not found")
    return Job(**row)

@api_router.get("/jobs/{job_id}/events")
async def get_events(job_id: str):
    return await db.job_events.find({"job_id": job_id}, {"_id": 0}).sort("created_at", 1).to_list(100)

@api_router.patch("/jobs/{job_id}/script", response_model=Job)
async def edit_script(job_id: str, body: ScriptUpdate):
    result = await db.video_jobs.update_one({"id": job_id, "status": {"$in": ["voice_required", "failed"]}}, {"$set": {"script": body.script, "caption": body.script[:220], "updated_at": now()}})
    if not result.modified_count:
        raise HTTPException(409, "Script can only be edited before voice upload")
    await add_event(job_id, "script_edited", "Operator edited the Hindi script before recording")
    row = await db.video_jobs.find_one({"id": job_id}, {"_id": 0})
    return Job(**row)

@api_router.post("/jobs/{job_id}/voice", response_model=Job)
async def upload_voice(job_id: str, file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    row = await db.video_jobs.find_one({"id": job_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Job not found")
    if file.content_type not in {"audio/wav", "audio/mpeg", "audio/mp4", "audio/webm", "audio/ogg"}:
        raise HTTPException(415, "Upload WAV, MP3, M4A, WebM, or OGG audio")
    audio_bytes = await file.read()
    await db.media_assets.update_one(
        {"job_id": job_id, "kind": "voice"},
        {"$set": {"job_id": job_id, "kind": "voice", "filename": file.filename, "content": audio_bytes, "content_type": file.content_type}},
        upsert=True,
    )
    temp_audio = tempfile.NamedTemporaryFile(prefix=f"{job_id}-", suffix=Path(file.filename or '').suffix or ".audio", delete=False)
    temp_audio.write(audio_bytes)
    temp_audio.close()
    path = Path(temp_audio.name)
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], check=True, capture_output=True, text=True)
        duration = float(probe.stdout.strip())
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "Audio duration could not be validated") from exc
    if not 3 <= duration <= 45:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "Voice recording must be between 3 and 45 seconds")
    await update_job(job_id, "composing", voice_filename=file.filename, voice_duration=round(duration, 2), voice_path=str(path))
    async def finish_render() -> None:
        try:
            await update_job(job_id, "validating")
            out, thumb = await asyncio.to_thread(render_video, job_id, row.get("script", ""), row["brief"]["duration_seconds"], path)
            await db.media_assets.insert_many([
                {"job_id": job_id, "kind": "video", "filename": out.name, "content": out.read_bytes(), "content_type": "video/mp4"},
                {"job_id": job_id, "kind": "thumbnail", "filename": thumb.name, "content": thumb.read_bytes(), "content_type": "image/jpeg"},
            ])
            out.unlink(missing_ok=True)
            thumb.unlink(missing_ok=True)
            await update_job(job_id, "ready_for_approval", video_url=f"/api/media/{out.name}", thumbnail_url=f"/api/media/{thumb.name}")
        except Exception as exc:
            logger.exception("render failed")
            await update_job(job_id, "failed", error=f"Render failed: {exc}")
    (background_tasks or BackgroundTasks()).add_task(finish_render)
    return Job(**(await db.video_jobs.find_one({"id": job_id}, {"_id": 0})))

@api_router.post("/jobs/{job_id}/approve", response_model=Job)
async def approve_job(job_id: str):
    result = await db.video_jobs.update_one({"id": job_id, "status": "ready_for_approval"}, {"$set": {"approved": True, "status": "approved", "updated_at": now()}})
    if not result.modified_count:
        raise HTTPException(409, "Only a ready render can be approved")
    await add_event(job_id, "approved", "Render approved for the next publishing phase")
    return Job(**(await db.video_jobs.find_one({"id": job_id}, {"_id": 0})))

@api_router.get("/media/{filename}")
async def media(filename: str):
    asset = await db.media_assets.find_one({"filename": filename, "kind": {"$in": ["video", "thumbnail"]}}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Media not found")
    return Response(content=asset["content"], media_type=asset["content_type"])

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])