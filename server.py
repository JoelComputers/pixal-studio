"""Loopback-only image-to-3D studio; all GPU work joins ComfyUI's queue."""
import argparse
import asyncio
import io
import json
import mimetypes
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pipeline import PRESETS, STAGES, build_graph
from settings import load_settings

ROOT = Path(__file__).resolve().parent
SETTINGS = load_settings()
DATA = SETTINGS["data_dir"]
JOBS_DIR = DATA / "jobs"
STATIC = ROOT / "static"
COMFY = SETTINGS["comfy_url"]
OUTPUT = SETTINGS["output_dir"]
LOCK = threading.RLock()
JOBS = {}
HEALTH = {"app": "pixal-studio", "online": False, "running": 0, "waiting": 0}
MAX_UPLOAD = 25 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 30_000_000


def comfy(path, payload=None, timeout=15):
    req = urllib.request.Request(COMFY + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"ComfyUI rejected the request: {detail[:2500]}") from exc


def save_job(job):
    target = JOBS_DIR / (job["id"] + ".json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(job, indent=2), encoding="utf-8")
    temporary.replace(target)


def public(job):
    fields = ("id", "name", "preset", "seed", "created", "status", "stage",
              "step", "steps", "ahead", "error", "duration", "files", "settings")
    result = {key: job[key] for key in fields if key in job}
    result["files"] = {key: {"name": value["name"], "bytes": value["bytes"]}
                       for key, value in job.get("files", {}).items()}
    return result


def upload_image(data, job_id):
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
            if min(image.size) < 64:
                raise ValueError("Use an image at least 64 pixels wide and tall.")
            if max(image.size) > 4096:
                image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            image.save(stream, "PNG")
            normalized = stream.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Upload a valid PNG, JPEG, or WebP image.") from exc
    source_path = DATA / (job_id + ".png")
    source_path.write_bytes(normalized)
    boundary = "pixal" + uuid.uuid4().hex
    filename = "pixal_gui_" + job_id + ".png"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body += normalized + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(COMFY + "/upload/image", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    return "/".join(filter(None, (result.get("subfolder"), result["name"])))


def submit(data, name, preset, seed):
    if preset not in PRESETS:
        raise ValueError("Unknown quality preset.")
    seed = int(seed)
    if not 0 <= seed <= 2147483647:
        raise ValueError("Seed is outside the allowed range.")
    job_id = uuid.uuid4().hex
    image = upload_image(data, job_id)
    graph = build_graph(image, preset, seed, job_id, models=SETTINGS["models"])
    definitions = comfy("/object_info", timeout=30)
    missing = sorted({n["class_type"] for n in graph.values()} - definitions.keys())
    if missing:
        raise ValueError("Missing ComfyUI nodes: " + ", ".join(missing))
    for node in graph.values():
        required = definitions[node["class_type"]]["input"].get("required", {})
        absent = set(required) - node["inputs"].keys()
        if absent:
            raise ValueError(f"Missing {node['class_type']} inputs: {sorted(absent)}")
    result = comfy("/prompt", {"prompt": graph}, timeout=30)
    if result.get("node_errors"):
        raise ValueError(str(result["node_errors"]))
    job = {"id": job_id, "prompt_id": result["prompt_id"], "name": name[:120],
           "preset": preset, "seed": seed, "settings": PRESETS[preset],
           "created": datetime.now(timezone.utc).isoformat(), "status": "queued",
           "stage": "Waiting for a GPU turn", "files": {}, "graph": graph}
    with LOCK:
        JOBS[job_id] = job
        save_job(job)
    return public(job)


def finish_job(job, entry):
    status = entry.get("status", {})
    messages = status.get("messages", [])
    errors = [(event, detail) for event, detail in messages
              if event in ("execution_error", "execution_interrupted")]
    if errors:
        event, detail = errors[-1]
        job["status"] = "cancelled" if event == "execution_interrupted" else "failed"
        job["error"] = detail.get("exception_message", "Generation was cancelled.").strip()
        job["stage"] = "Cancelled" if job["status"] == "cancelled" else "Generation failed"
    elif status.get("status_str") == "success":
        outputs = entry.get("outputs", {})
        for node, kind, key in (("61", "3d", "model"), ("60", "3d", "clean"),
                ("65", "3d", "source_mesh"), ("66", "images", "base_color"),
                ("67", "images", "metallic"), ("68", "images", "roughness"),
                ("71", "images", "prepared")):
            values = outputs.get(node, {}).get(kind, [])
            if values:
                value = values[0]
                target = (OUTPUT / value.get("subfolder", "") / value["filename"]).resolve()
                if not target.is_relative_to(OUTPUT) or not target.is_file():
                    raise RuntimeError("Generated file is unavailable in the configured output folder.")
                job["files"][key] = {"path": str(target), "name": target.name,
                                     "bytes": target.stat().st_size}
        if "model" not in job["files"]:
            raise RuntimeError("ComfyUI completed without exporting the finished model.")
        job.update(status="completed", stage="Ready to explore")
    else:
        job.update(status="failed", error="ComfyUI did not complete the job.")
    stamps = {event: detail.get("timestamp") for event, detail in messages}
    if stamps.get("execution_start") and stamps.get("execution_success"):
        job["duration"] = round((stamps["execution_success"] - stamps["execution_start"]) / 1000, 1)
    job.pop("ahead", None)
    job.pop("step", None)
    job.pop("steps", None)
    save_job(job)
    (JOBS_DIR / (job["id"] + ".history.json")).write_text(json.dumps(entry), encoding="utf-8")


def poll():
    while True:
        try:
            queue = comfy("/queue", timeout=5)
            running = {row[1] for row in queue["queue_running"]}
            pending = [row[1] for row in queue["queue_pending"]]
            with LOCK:
                HEALTH.update(online=True, running=len(running), waiting=len(pending))
                active = [j for j in JOBS.values()
                          if j["status"] not in ("completed", "failed", "cancelled")]
            for job in active:
                pid = job["prompt_id"]
                history = comfy("/history/" + pid, timeout=5)
                with LOCK:
                    if pid in history:
                        try:
                            finish_job(job, history[pid])
                        except Exception as exc:
                            job.update(status="failed", error=str(exc))
                            save_job(job)
                    elif pid in running:
                        job["status"] = "cancelling" if job.get("cancel_requested") else "running"
                        if job["stage"] == "Waiting for a GPU turn":
                            job["stage"] = "Starting generation"
                        job.pop("ahead", None)
                    elif pid in pending:
                        job.update(status="queued", ahead=len(running) + pending.index(pid),
                                   stage="Waiting for a GPU turn")
                    elif job.get("cancel_requested"):
                        job.update(status="cancelled", stage="Cancelled")
                        save_job(job)
                    else:
                        # Wait through brief queue/history transitions, then report
                        # an actual restart or removed job instead of waiting forever.
                        job["missing_polls"] = job.get("missing_polls", 0) + 1
                        if job["missing_polls"] >= 4:
                            job.update(status="failed", error="The job disappeared from ComfyUI. It may have been restarted or removed from the queue.")
                            save_job(job)
        except Exception:
            with LOCK:
                HEALTH["online"] = False
        time.sleep(2)


async def progress_listener():
    import aiohttp
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(COMFY + "/ws") as ws:
                    async for message in ws:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        event = json.loads(message.data)
                        data = event.get("data", {})
                        with LOCK:
                            job = next((j for j in JOBS.values()
                                if j["prompt_id"] == data.get("prompt_id")), None)
                            if not job or job["status"] in ("completed", "failed", "cancelled"):
                                continue
                            if event["type"] == "progress_state":
                                active = [v for v in data.get("nodes", {}).values()
                                          if v["state"] == "running"]
                                if active:
                                    node = active[-1]
                                    job.update(stage=STAGES.get(node["node_id"], "Preparing model"),
                                               step=node["value"], steps=node["max"])
                            elif event["type"] == "progress":
                                job.update(stage=STAGES.get(data.get("node"), "Generating"),
                                           step=data["value"], steps=data["max"])
        except Exception:
            await asyncio.sleep(3)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith("POST"):
            super().log_message(fmt, *args)

    def local(self):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        return host in allowed and self.headers.get("Origin", "http://" + host) in {
            "http://" + h for h in allowed}

    def respond(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def file(self, path, download=False):
        if not path.is_file():
            return self.respond({"error": "File not found."}, 404)
        self.send_response(200)
        mime = {".js": "text/javascript", ".glb": "model/gltf-binary"}.get(
            path.suffix, mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Type", mime)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(path.stat().st_size))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as stream:
            while data := stream.read(1024 * 1024):
                self.wfile.write(data)

    def do_GET(self):
        if not self.local():
            return self.respond({"error": "Local access only."}, 403)
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        try:
            if path == "/api/status":
                with LOCK:
                    return self.respond(dict(HEALTH))
            if path == "/api/jobs":
                with LOCK:
                    return self.respond({"jobs": [public(j) for j in sorted(
                        JOBS.values(), key=lambda j: j["created"], reverse=True)]})
            if path.startswith("/file/"):
                _, _, job_id, kind = path.split("/")
                with LOCK:
                    job = JOBS.get(job_id)
                    if not job:
                        return self.respond({"error": "Unknown job."}, 404)
                    if kind == "source":
                        target = DATA / (job_id + ".png")
                    else:
                        record = job.get("files", {}).get(kind)
                        if not record:
                            return self.respond({"error": "This file is not ready yet."}, 404)
                        target = Path(record["path"]).resolve()
                        if not target.is_relative_to(OUTPUT):
                            return self.respond({"error": "Invalid output path."}, 403)
                return self.file(target, "download" in urllib.parse.parse_qs(url.query))
            if path.startswith("/vendor/"):
                base = ROOT / "vendor" / "three"
                if not base.is_dir():
                    base = ROOT / "node_modules" / "three"
                target = (base / path[len("/vendor/"):]).resolve()
            else:
                base = STATIC
                target = (base / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not target.is_relative_to(base.resolve()):
                return self.respond({"error": "Not found."}, 404)
            return self.file(target)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (KeyError, ValueError):
            self.respond({"error": "Not found."}, 404)

    def do_POST(self):
        if not self.local():
            return self.respond({"error": "Local access only."}, 403)
        url = urllib.parse.urlsplit(self.path)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 <= size <= MAX_UPLOAD:
                return self.respond({"error": "Choose an image smaller than 25 MB."}, 413)
            body = self.rfile.read(size)
            if url.path == "/api/jobs":
                query = urllib.parse.parse_qs(url.query)
                name = query.get("name", ["Untitled model"])[0]
                preset = query.get("preset", ["detail"])[0]
                seed = query.get("seed", ["42"])[0]
                return self.respond(submit(body, name, preset, seed), 201)
            parts = url.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
                with LOCK:
                    job = JOBS.get(parts[2])
                    if not job:
                        return self.respond({"error": "Unknown job."}, 404)
                    pid = job["prompt_id"]
                result = comfy(f"/api/jobs/{pid}/cancel", {})
                with LOCK:
                    if result.get("cancelled"):
                        job.update(cancel_requested=True, status="cancelling", stage="Cancelling this job")
                        save_job(job)
                    return self.respond(public(job))
            self.respond({"error": "Not found."}, 404)
        except ValueError as exc:
            self.respond({"error": str(exc)}, 400)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            self.respond({"error": f"Cannot reach ComfyUI at {COMFY}. Start it, then try again."}, 503)
        except Exception as exc:
            self.respond({"error": str(exc)}, 500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    for path in JOBS_DIR.glob("*.json"):
        if path.name.endswith(".history.json"):
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            JOBS[job["id"]] = job
        except (KeyError, ValueError):
            pass
    threading.Thread(target=poll, daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(progress_listener()), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Pixal Studio: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
