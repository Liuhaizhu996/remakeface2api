#!/usr/bin/env python3
"""
RemakeFace WebUI backend — local API gateway to AppBMS ai-image-gen.

Endpoints:
  GET  /                    -> WebUI (static/index.html)
  GET  /api/health          -> service + device-session status
  GET  /api/models          -> built-in model list
  GET  /api/ratios          -> supported aspect ratios
  POST /api/generate        -> multipart: file?(reference), prompt, model, ratio
                               returns {jobId} immediately
  GET  /api/jobs/{jobId}    -> {status: pending|completed|failed, ...}
  GET  /api/image/{name}    -> cached generated image
  GET  /api/history         -> recent generations
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))
import remake_client as rc

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "device_state.json"
STATIC_DIR = SERVER_DIR / "static"
DATA_DIR = SERVER_DIR / "data"
GEN_DIR = DATA_DIR / "generated"

GEN_DIR.mkdir(parents=True, exist_ok=True)
JOBS_PATH = DATA_DIR / "jobs.json"


def _load_jobs() -> dict:
    try:
        if JOBS_PATH.exists():
            return json.loads(JOBS_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_jobs():
    try:
        JOBS_PATH.write_text(json.dumps(_jobs, ensure_ascii=False, indent=1))
    except Exception:
        pass


MODELS = [
    {"id": "general_v4.0_s", "name": "General v4.0 (Fast)", "description": "通用平衡模型（默认，速度快）"},
    {"id": "general_v4.0",   "name": "General v4.0",        "description": "通用高质量版本"},
    {"id": "general_v3.0",   "name": "General v3.0",        "description": "上一代通用模型"},
    {"id": "general_v2.0",   "name": "General v2.0",        "description": "通用模型（旧版）"},
    {"id": "general_v1.0",   "name": "General v1.0",        "description": "通用模型（初版）"},
    {"id": "portrait_v3.2",  "name": "Portrait v3.2",       "description": "人像/肤色/光影优化"},
    {"id": "portrait_v3.0",  "name": "Portrait v3.0",       "description": "人像优化版"},
    {"id": "portrait_v2.0",  "name": "Portrait v2.0",       "description": "人像模型（旧版）"},
    {"id": "portrait_v1.0",  "name": "Portrait v1.0",       "description": "人像模型（初版）"},
    {"id": "fantasy_v2.1",   "name": "Fantasy v2.1",        "description": "幻想场景风格化"},
    {"id": "fantasy_v2.0",   "name": "Fantasy v2.0",        "description": "幻想场景（旧版）"},
    {"id": "fantasy_v1.0",   "name": "Fantasy v1.0",        "description": "幻想场景（初版）"},
    {"id": "anime_v2.0",     "name": "Anime v2.0",          "description": "二次元动漫风格（新版）"},
    {"id": "realistic_v2.0", "name": "Realistic v2.0",      "description": "写实摄影风格（新版）"},
    {"id": "3d_v2.0",        "name": "3D Render v2.0",      "description": "3D 渲染风格（新版）"},
    {"id": "anime_v1.0",     "name": "Anime v1.0",          "description": "二次元动漫风格"},
    {"id": "realistic_v1.0", "name": "Realistic v1.0",      "description": "写实摄影风格"},
    {"id": "cartoon_v1.0",   "name": "Cartoon v1.0",       "description": "卡通漫画风格"},
    {"id": "digital_v1.0",   "name": "Digital Art v1.0",   "description": "数字插画风格"},
    {"id": "sketch_v1.0",    "name": "Sketch v1.0",        "description": "素描/线稿风格"},
    {"id": "oil_v1.0",       "name": "Oil Painting v1.0",  "description": "油画风格"},
    {"id": "cyberpunk_v1.0", "name": "Cyberpunk v1.0",     "description": "赛博朋克霓虹夜景风格"},
    {"id": "cinematic_v1.0", "name": "Cinematic v1.0",     "description": "电影感构图与光影"},
    {"id": "3d_v1.0",        "name": "3D Render v1.0",      "description": "3D 渲染风格"},
]
RATIOS = ["Original", "1:1", "4:3", "3:4", "9:16", "16:9"]
MAX_PROMPT = 20000

app = FastAPI(title="RemakeFace WebUI", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_client_lock = threading.Lock()
_client: rc.RemakeClient | None = None

_jobs: dict[str, dict] = _load_jobs()
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=2)

MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
}


def get_client() -> rc.RemakeClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = rc.RemakeClient(str(STATE_PATH))
        return _client


def _normalize_image(data: bytes) -> tuple[bytes, str]:
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), "image/jpeg"


def _upload(data: bytes, name: str) -> str:
    c = get_client()
    c.sync_time()
    c.ensure_session()
    return c.upload_image("ai-image-gen-image", data, name, "image/jpeg")


def _run_generation(job_id: str, prompt: str, model: str, ratio: str, image_data: bytes | None, filename: str):
    try:
        c = get_client()
        c.sync_time()
        c.ensure_session()
        keys = []
        if image_data is not None:
            norm, ct = _normalize_image(image_data)
            key = c.upload_image("ai-image-gen-image", norm, filename or "ref.jpg", ct)
            keys.append(key)
        job, su, resp = c.ai_image_gen(keys, prompt, ratio, model)
        result = c.poll(su, job, poll_after_ms=3000, timeout_s=360)
        state = result.get("state") or result.get("status")
        if state and state.lower() in ("failed", "error", "cancelled", "canceled"):
            raise RuntimeError(f"AppBMS job failed: {result.get('failedReason') or result}")
        res = result.get("result") or {}
        urls = []
        if isinstance(res, str) and res.startswith("http"):
            urls = [res]
        elif isinstance(res, dict):
            urls = [u for u in (res.get("imageUrls") or res.get("urls") or [])
                    if isinstance(u, str) and u.startswith("http")]
            if not urls:
                for v in res.values():
                    if isinstance(v, list):
                        urls = [u for u in v if isinstance(u, str) and u.startswith("http")]
                        if urls:
                            break
        if not urls:
            raise RuntimeError(f"no image url in result: {result}")
        local_urls = []
        for i, u in enumerate(urls):
            name = f"{job_id}_{i}{Path(u).suffix or '.png'}"
            dest = GEN_DIR / name
            import urllib.request
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "okhttp/4.12.0"}), timeout=180) as r:
                raw = r.read()
            dest.write_bytes(raw)
            local_urls.append(f"/api/image/{name}")
        with _jobs_lock:
            _jobs[job_id] = {"status": "completed", "prompt": prompt, "model": model,
                             "ratio": ratio, "imageUrls": local_urls, "updatedAt": int(time.time()*1000)}
            _save_jobs()
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id] = {"status": "failed", "error": str(e), "updatedAt": int(time.time()*1000)}
            _save_jobs()


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health():
    try:
        c = get_client()
        c.sync_time()
        sess = c.ensure_session()
        return {
            "ok": True,
            "service": "remakeface-appbms",
            "session": sess.get("deviceSessionId"),
            "trustLevel": sess.get("trustLevel"),
            "ttlSeconds": sess.get("ttlSeconds"),
            "serverOffsetMs": c.server_offset_ms,
            "models": [m["id"] for m in MODELS],
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)})


@app.get("/api/models")
def models():
    return {"models": MODELS}


@app.get("/api/ratios")
def ratios():
    return {"ratios": RATIOS}


@app.post("/api/generate")
async def generate(
    file: UploadFile | None = File(None),
    prompt: str = Form(..., min_length=1),
    model: str = Form("general_v4.0_s"),
    ratio: str = Form("1:1"),
):
    if len(prompt) > MAX_PROMPT:
        raise HTTPException(400, f"prompt too long (max {MAX_PROMPT})")
    if model not in {m["id"] for m in MODELS}:
        raise HTTPException(400, f"unknown model: {model}. available: {[m['id'] for m in MODELS]}")
    if ratio not in RATIOS:
        raise HTTPException(400, f"unknown ratio: {ratio}. available: {RATIOS}")
    image_data = None
    filename = None
    if file is not None and file.filename:
        image_data = await file.read()
        if not image_data:
            raise HTTPException(400, "empty file")
        filename = file.filename
    job_id = uuid.uuid4().hex[:16]
    with _jobs_lock:
        _jobs[job_id] = {"status": "pending", "prompt": prompt, "model": model,
                         "ratio": ratio, "updatedAt": int(time.time()*1000)}
    _save_jobs()
    _pool.submit(_run_generation, job_id, prompt, model, ratio, image_data, filename)
    return {"jobId": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/image/{name}")
def image(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad name")
    p = GEN_DIR / name
    if not p.exists():
        raise HTTPException(404, "image not found")
    return FileResponse(str(p), media_type=MIME.get(p.suffix.lower(), "application/octet-stream"))


@app.get("/api/history")
def history(limit: int = 20):
    items = []
    with _jobs_lock:
        for jid, j in _jobs.items():
            items.append({"jobId": jid, **j})
    items.sort(key=lambda x: x.get("updatedAt", 0), reverse=True)
    return {"items": items[:limit]}


def _sync_generate(prompt: str, model: str, ratio: str, image_data: bytes | None, filename: str):
    c = get_client()
    c.sync_time()
    c.ensure_session()
    keys = []
    if image_data is not None:
        norm, ct = _normalize_image(image_data)
        key = c.upload_image("ai-image-gen-image", norm, filename or "ref.jpg", ct)
        keys.append(key)
    job, su, resp = c.ai_image_gen(keys, prompt, ratio, model)
    result = c.poll(su, job, poll_after_ms=3000, timeout_s=360)
    state = result.get("state") or result.get("status")
    if state and state.lower() in ("failed", "error", "cancelled", "canceled"):
        raise RuntimeError(f"AppBMS job failed: {result.get('failedReason') or result}")
    res = result.get("result") or {}
    urls = []
    if isinstance(res, str) and res.startswith("http"):
        urls = [res]
    elif isinstance(res, dict):
        urls = [u for u in (res.get("imageUrls") or res.get("urls") or [])
                if isinstance(u, str) and u.startswith("http")]
        if not urls:
            for v in res.values():
                if isinstance(v, list):
                    urls = [u for u in v if isinstance(u, str) and u.startswith("http")]
                    if urls:
                        break
    if not urls:
        raise RuntimeError(f"no image url in result: {result}")
    import urllib.request
    out = []
    for i, u in enumerate(urls):
        name = f"v1_{int(time.time()*1000)}_{i}{Path(u).suffix or '.png'}"
        dest = GEN_DIR / name
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "okhttp/4.12.0"}), timeout=180) as r:
            raw = r.read()
        dest.write_bytes(raw)
        out.append(f"/api/image/{name}")
    return out


SIZE_MAP = {
    "1024x1024": "1:1", "512x512": "1:1", "256x256": "1:1",
    "1024x1792": "9:16", "1792x1024": "16:9",
    "768x1024": "3:4", "1024x768": "4:3",
}


@app.get("/v1/models")
def openai_models():
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "created": created,
                "owned_by": "appbms-remakeface",
                "root": m["id"],
                "permission": [],
            }
            for m in MODELS
        ],
    }


@app.post("/v1/images/generations")
async def openai_generate(payload: dict):
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is required")
    if len(prompt) > MAX_PROMPT:
        raise HTTPException(400, f"prompt too long (max {MAX_PROMPT})")
    model = str(payload.get("model") or "general_v4.0_s")
    if model not in {m["id"] for m in MODELS}:
        raise HTTPException(400, f"unknown model: {model}. available: {[m['id'] for m in MODELS]}")
    size = str(payload.get("size") or "1024x1024")
    ratio = SIZE_MAP.get(size, size if size in RATIOS else "1:1")
    if ratio not in RATIOS:
        ratio = "1:1"
    n = int(payload.get("n") or 1)
    if n < 1 or n > 4:
        raise HTTPException(400, "n must be 1..4")
    try:
        images = []
        for _ in range(n):
            urls = await run_in_threadpool(_sync_generate, prompt, model, ratio, None, None)
            for u in urls:
                images.append({"url": u})
        now = int(time.time()*1000)
        with _jobs_lock:
            for u in images:
                job_id = uuid.uuid4().hex[:16]
                _jobs[job_id] = {"status": "completed", "prompt": prompt, "model": model,
                                 "ratio": ratio, "imageUrls": [u.get("url") if isinstance(u, dict) else u],
                                 "updatedAt": now}
            _save_jobs()
        return {"created": int(time.time()), "data": images}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"generation failed: {e}")


from starlette.concurrency import run_in_threadpool


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8610")))
