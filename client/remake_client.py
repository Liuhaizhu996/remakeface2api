#!/usr/bin/env python3
"""
RemakeFace AppBMS backend client (clean-room reimplementation).
Protocol recovered from RemakeFace Ai V1.3.2 PRO.apk (Pairip/R8 smali):

  POST /v1/device-sessions/challenges
      {platform:"android", appIdentifier, packageName, installationId, appVersion}
      -> {challengeId, challenge, deviceSessionAttestationRequired, enabledAttestationProviders, ttlSeconds}

  POST /v1/device-sessions   (header X-Attestation-Recovery-Version: 1)
      {platform, appIdentifier, packageName, challengeId, publicKeyPem, installationId, appVersion}
      -> {deviceSessionId, expiresInSeconds|ttlSeconds, trustLevel, packageName, ...}

  Signed request headers (X-Signed-Recovery-Version: 1 for POST):
      X-Device-Session-Id: <deviceSessionId>
      X-Request-Timestamp: <unix_ms + server_offset>
      X-Request-Nonce:     <16 random bytes, base64url-nopad>
      X-Body-SHA256:       <base64url-nopad(sha256(body))>
      X-Device-Signature:  <base64url-nopad(ECDSA-SHA256(sign_string))>
  sign_string = "\n".join([METHOD.upper(), PATH, timestamp, nonce, deviceSessionId, bodyHashB64])
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import secrets
import uuid
import sys
import time
import urllib.request
import urllib.error
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes

BASE = "https://api.appbms.com"
APP_ID = "com.photoeditor.remakemefaceswapaigenerator"
APP_VERSION = "1.3.2"
PKG = APP_ID

B64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")


def pem_public(der_public: bytes) -> str:
    """Format like Android Keystore PEM: '-----BEGIN PUBLIC KEY-----' wrapped at 64 (DER input)."""
    b64 = base64.b64encode(der_public).decode()
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"


class RemakeClient:
    def __init__(self, state_path: str | None = None):
        self.state_path = state_path
        self.state = {"installation_id": str(uuid.uuid4())}
        self.private_key: ec.EllipticCurvePrivateKey | None = None
        self.session: dict | None = None      # deviceSessionId etc
        self.server_offset_ms = 0
        if state_path and os.path.exists(state_path):
            with open(state_path) as f:
                self.state.update(json.load(f))
            if self.state.get("private_key_pem"):
                self.private_key = serialization.load_pem_private_key(
                    self.state["private_key_pem"].encode(), password=None)
            if self.state.get("session"):
                self.session = self.state["session"]
            if self.state.get("server_offset_ms"):
                self.server_offset_ms = self.state["server_offset_ms"]

    def _save(self):
        if not self.state_path:
            return
        # A fresh git clone does not contain runtime state directories.
        # Create the parent lazily so first-run registration can persist safely.
        os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
        self.state["private_key_pem"] = self.private_key and self.private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        self.state["session"] = self.session
        self.state["server_offset_ms"] = self.server_offset_ms
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, self.state_path)

    # ---------- HTTP ----------
    def _req(self, method: str, path: str, body: dict | None = None, signed: bool = False,
             extra_headers: dict | None = None) -> tuple[int, dict | str]:
        url = BASE + path
        data = None
        body_b64 = B64(hashlib.sha256(b"").digest())
        if body is not None:
            raw = json.dumps(body, separators=(",", ":")).encode()
            body_b64 = B64(hashlib.sha256(raw).digest())
            data = raw
        headers = {"Content-Type": "application/json", "User-Agent": "okhttp/4.12.0"}
        if extra_headers:
            headers.update(extra_headers)
        if signed:
            if not self.session or not self.private_key:
                raise RuntimeError("device session required")
            ts = str(int(time.time() * 1000) + self.server_offset_ms)
            nonce = B64(os.urandom(16))
            to_sign = "\n".join([method.upper(), path, ts, nonce,
                                 self.session["deviceSessionId"], body_b64])
            sig = self.private_key.sign(to_sign.encode(), ec.ECDSA(hashes.SHA256()))
            headers.update({
                "X-Device-Session-Id": self.session["deviceSessionId"],
                "X-Request-Timestamp": ts,
                "X-Request-Nonce": nonce,
                "X-Body-SHA256": body_b64,
                "X-Device-Signature": B64(sig),
            })
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                ct = r.headers.get("content-type", "")
                return r.status, (json.loads(raw) if "json" in ct else raw.decode())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw.decode()

    # ---------- protocol ----------
    def sync_time(self) -> None:
        code, resp = self._req("GET", "/v1/time")
        if code == 200 and isinstance(resp, dict) and "serverTimeMs" in resp:
            self.server_offset_ms = resp["serverTimeMs"] - int(time.time() * 1000)
            self._save()

    def get_challenge(self) -> dict:
        code, resp = self._req("POST", "/v1/device-sessions/challenges", {
            "platform": "android",
            "appIdentifier": APP_ID,
            "packageName": PKG,
            "installationId": self.state["installation_id"],
            "appVersion": APP_VERSION,
        })
        if code != 201 and code != 200:
            raise RuntimeError(f"challenge failed {code}: {resp}")
        return resp

    def ensure_key(self):
        if self.private_key is None:
            self.private_key = ec.generate_private_key(ec.SECP256R1())
            self._save()

    def register(self) -> dict:
        self.ensure_key()
        chal = self.get_challenge()
        pub = self.private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        body = {
            "platform": "android",
            "appIdentifier": APP_ID,
            "packageName": PKG,
            "challengeId": chal["challengeId"],
            "publicKeyPem": pem_public(pub),
            "installationId": self.state["installation_id"],
            "appVersion": APP_VERSION,
        }
        code, resp = self._req("POST", "/v1/device-sessions", body,
                               extra_headers={"X-Attestation-Recovery-Version": "1"})
        if code not in (200, 201):
            raise RuntimeError(f"register failed {code}: {resp}")
        if isinstance(resp, dict) and "deviceSessionId" in resp:
            ttl = resp.get("expiresInSeconds") or resp.get("ttlSeconds") or 86400
            resp.setdefault("expiresAtMs", int(time.time() * 1000) + int(ttl) * 1000)
            self.session = resp
            self._save()
            return resp
        raise RuntimeError(f"register unexpected {code}: {resp}")

    def ensure_session(self):
        if self.session and self.private_key:
            exp = self.session.get("expiresAtMs", 0)
            if exp - int(time.time() * 1000) > 60_000:
                return self.session
        self.register()
        return self.session

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
        self.ensure_session()
        code, resp = self._req(method, path, body, signed=True,
                               extra_headers={"X-Signed-Recovery-Version": "1"})
        if code == 401 and isinstance(resp, dict):
            err = resp.get("error", {})
            if isinstance(err, dict) and err.get("code") in (
                    "DEVICE_SESSION_REFRESH_REQUIRED", "DEVICE_SESSION_INVALID",
                    "SESSION_INVALID", "SIGNATURE_INVALID", "UNAUTHORIZED"):
                self.session = None
                self.register()
                code, resp = self._req(method, path, body, signed=True,
                                       extra_headers={"X-Signed-Recovery-Version": "1"})
        return code, resp

    # ---------- AI model calls ----------
    def upload_image(self, purpose: str, data: bytes, filename: str, content_type: str | None = None) -> str:
        """Returns imageKey (S3 key) after uploading bytes."""
        if not content_type:
            ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "jpg"
            content_type = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg",
                            "jpeg": "image/jpeg", "heic": "image/heic", "heif": "image/heif"}.get(ext, "image/jpeg")
        code, resp = self.call("POST", "/v1/storage/s3/presigned-url", {
            "purpose": purpose,
            "contentType": content_type,
            "fileName": filename,
            "contentLength": len(data),
        })
        if code not in (200, 201) or not isinstance(resp, dict):
            raise RuntimeError(f"presign failed {code}: {resp}")
        method = resp.get("method", "PUT").upper()
        upload_url = resp["uploadUrl"]
        headers = {k: str(v) for k, v in (resp.get("headers") or {}).items()}
        req = urllib.request.Request(upload_url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status >= 300:
                    raise RuntimeError(f"upload failed {r.status}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"upload failed {e.code}: {e.read()[:200]}")
        return resp["key"]

    def _submit(self, path: str, body: dict) -> tuple[str, str | None, dict]:
        code, resp = self.call("POST", path, body)
        if code not in (200, 201, 202):
            raise RuntimeError(f"{path} failed {code}: {resp}")
        if isinstance(resp, str):
            resp = json.loads(resp)
        job = resp.get("jobId") or resp.get("id") or resp.get("taskId")
        if not job:
            raise RuntimeError(f"{path} no jobId: {resp}")
        status_url = resp.get("statusUrl") or resp.get("jobStatusUrl")
        return job, status_url, resp

    def get_many_faces(self, image_key: str, versi: str = "v3") -> tuple[str, str | None, dict]:
        return self._submit("/v1/ai/get-many-faces", {"imageKey": image_key, "versi": versi})

    def check_nsfw(self, image_key: str, source: str = "image") -> tuple[str, str | None, dict]:
        return self._submit("/v1/ai/check-nsfw", {"imageKey": image_key, "source": source})

    def ai_image_gen(self, image_keys: list[str], prompt: str, image_ratio: str, model: str) -> tuple[str, str | None, dict]:
        return self._submit("/v1/ai/ai-image-gen", {
            "imagePathList": image_keys, "prompt": prompt, "imageRatio": image_ratio, "model": model,
        })

    def face_swap(self, source_key: str, target_key: str, queue_type: str = "standard",
                  versi: str = "v3", is_enhance: bool = False) -> tuple[str, str | None, dict]:
        return self._submit("/v1/ai/face-swap", {
            "sourceImagePath": source_key, "targetImagePath": target_key,
            "queueType": queue_type, "versi": versi, "isEnhance": is_enhance,
        })

    def multi_face_swap(self, image_resource_paths: list[str], target_key: str, faces_to_swap: list,
                        queue_type: str = "standard", versi: str = "v3", is_enhance: bool = False) -> tuple[str, str | None, dict]:
        return self._submit("/v1/ai/multi-face-swap", {
            "imageResourcePaths": image_resource_paths, "targetImagePath": target_key,
            "facesToSwap": faces_to_swap, "queueType": queue_type, "versi": versi, "isEnhance": is_enhance,
        })

    def poll(self, status_url: str | None, job_id: str, poll_after_ms: int = 3000,
             timeout_s: int = 180) -> dict:
        """Poll a task until terminal state. status_url may be absolute or relative."""
        import time as _t
        deadline = _t.time() + timeout_s
        while _t.time() < deadline:
            url = status_url if (status_url and status_url.startswith("http")) else (BASE + status_url if status_url else None)
            path = url.split(BASE, 1)[-1] if url and url.startswith(BASE) else (url or f"/v1/ai/jobs/{job_id}")
            code, resp = self.call("GET", path)
            if code == 200:
                if isinstance(resp, str):
                    try:
                        resp = json.loads(resp)
                    except Exception:
                        pass
                status = (resp.get("status") or resp.get("state") or "") if isinstance(resp, dict) else ""
                if status.lower() in ("completed", "succeeded", "success", "done", "ready", "finished"):
                    return resp
                if status.lower() in ("failed", "error", "cancelled", "canceled"):
                    raise RuntimeError(f"task failed: {resp}")
            _t.sleep(poll_after_ms / 1000.0)
        raise TimeoutError(f"task timeout job={job_id}")


if __name__ == "__main__":
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    c = RemakeClient(str(root / "state" / "device_state.json"))
    c.sync_time()
    print("time offset ms:", c.server_offset_ms)
    s = c.ensure_session()
    print("session:", json.dumps({k: v for k, v in s.items() if k != "raw"}, indent=2))
