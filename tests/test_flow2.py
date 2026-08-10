#!/usr/bin/env python3
"""E2E face-swap flow test: upload source+target -> face_swap -> poll -> download result."""
from __future__ import annotations
import json, os, sys, urllib.request
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "client"))
import remake_client as rc

def download(url: str, out: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/4.12.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    with open(out, "wb") as f:
        f.write(data)
    print(f"    downloaded {out} ({len(data)} bytes)")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tests/test_flow2.py /path/to/source.jpg [/path/to/target.jpg]")
        sys.exit(2)
    src_img = sys.argv[1]
    tgt_img = sys.argv[2] if len(sys.argv) > 2 else src_img
    c = rc.RemakeClient(str(pathlib.Path(__file__).resolve().parents[1] / "state" / "device_state.json"))
    c.sync_time()
    c.ensure_session()
    print(f"[ok] session active")

    def upload(p: str) -> str:
        data = open(p, "rb").read()
        ct = "image/png" if p.lower().endswith((".png", ".webp")) else "image/jpeg"
        k = c.upload_image("face-swap-source", data, os.path.basename(p), ct)
        print(f"[ok] upload {p} -> {k}")
        return k

    src_key = upload(src_img)
    tgt_key = upload(tgt_img)

    job, su, resp = c.face_swap(src_key, tgt_key, queue_type="standard", versi="v3", is_enhance=False)
    print(f"[ok] face_swap job={job} statusUrl={su}")

    result = c.poll(su, job, poll_after_ms=3000, timeout_s=300)
    state = result.get("state") or result.get("status")
    print(f"[ok] face_swap final state={state}")
    res = result.get("result") or {}
    print("    result keys:", sorted(res.keys()) if isinstance(res, dict) else res)

    # find output URL
    out_url = None
    if isinstance(res, str) and res.startswith("http"):
        out_url = res
    for k in ("imageUrl", "outputUrl", "resultUrl", "url", "output"):
        if isinstance(res, dict) and res.get(k):
            out_url = res[k]
            break
    if not out_url and isinstance(res, dict):
        for v in res.values():
            if isinstance(v, str) and v.startswith("http"):
                out_url = v
                break
            if isinstance(v, list) and v and isinstance(v[0], str) and v[0].startswith("http"):
                out_url = v[0]
                break
    if out_url:
        print(f"    output URL: {out_url}")
        download(out_url, "result_swap.png" if out_url.endswith((".png", ".webp")) else "result_swap.jpg")
        print("\n[PASS] face-swap E2E complete")
        return 0
    print("\n[WARN] completed but no output URL found in:", json.dumps(result, ensure_ascii=False)[:600])
    return 1

if __name__ == "__main__":
    sys.exit(main())
