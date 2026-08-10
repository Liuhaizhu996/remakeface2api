#!/usr/bin/env python3
"""AI image generation test: upload ref image -> ai-image-gen -> poll -> download."""
import json, os, sys, urllib.request
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "client"))
import remake_client as rc

def download(url, out):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "okhttp/4.12.0"}), timeout=120) as r:
        data = r.read()
    open(out, "wb").write(data)
    print(f"    downloaded {out} ({len(data)} bytes)")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tests/test_gen.py /path/to/image [prompt] [model] [ratio]")
        sys.exit(2)
    img = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "a cyberpunk portrait, neon lights, cinematic"
    model = sys.argv[3] if len(sys.argv) > 3 else "general_v4.0_s"
    ratio = sys.argv[4] if len(sys.argv) > 4 else "1:1"
    c = rc.RemakeClient(str(pathlib.Path(__file__).resolve().parents[1] / "state" / "device_state.json"))
    c.sync_time()
    c.ensure_session()
    data = open(img, "rb").read()
    ct = "image/png" if img.lower().endswith((".png", ".webp")) else "image/jpeg"
    key = c.upload_image("ai-image-gen-image", data, os.path.basename(img), ct)
    print(f"[ok] uploaded {img} -> {key}")

    job, su, resp = c.ai_image_gen([key], prompt, ratio, model)
    print(f"[ok] ai-image-gen job={job} statusUrl={su}")
    result = c.poll(su, job, poll_after_ms=3000, timeout_s=300)
    state = result.get("state") or result.get("status")
    print(f"[ok] ai-image-gen state={state}")
    res = result.get("result")
    print("    result:", json.dumps(res, ensure_ascii=False)[:500])

    out_url = None
    if isinstance(res, str) and res.startswith("http"):
        out_url = res
    elif isinstance(res, dict):
        for k in ("imageUrl", "outputUrl", "url", "output"):
            if res.get(k) and str(res[k]).startswith("http"):
                out_url = res[k]; break
        if not out_url:
            for v in res.values():
                if isinstance(v, list) and v and str(v[0]).startswith("http"):
                    out_url = v[0]; break
    if out_url:
        out = pathlib.Path(out_url)
        ext = out.suffix if out.suffix in (".png", ".jpg", ".jpeg", ".webp") else (".png" if "png" in out_url else ".jpg")
        dest = str(pathlib.Path(__file__).resolve().parents[1] / "examples" / ("ai_gen_output" + ext))
        download(out_url, dest)
        print("[PASS] ai-image-gen complete")
        return 0
    print("[WARN] no output url:", json.dumps(result, ensure_ascii=False)[:600])
    return 1

if __name__ == "__main__":
    sys.exit(main())
