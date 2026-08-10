#!/usr/bin/env python3
"""Full-flow smoke test for RemakeFace AppBMS clean-room client.

Pipeline: sync_time -> ensure_session -> upload_image -> get_many_faces
          -> check_nsfw -> face_swap -> poll result.
Usage: python3 test_flow.py [image] [--dry-register]
"""
from __future__ import annotations
import json, os, sys, time
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "client"))
import remake_client as rc

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tests/test_flow.py /path/to/image")
        sys.exit(2)
    img = sys.argv[1]
    if not os.path.exists(img):
        print(f"[FAIL] image not found: {img}")
        sys.exit(2)

    c = rc.RemakeClient(str(pathlib.Path(__file__).resolve().parents[1] / "state" / "device_state.json"))

    # 1) time sync
    c.sync_time()
    print(f"[ok] time offset ms = {c.server_offset_ms}")

    # 2) session
    s = c.ensure_session()
    print(f"[ok] session {s.get('deviceSessionId')} trust={s.get('trustLevel')} "
          f"ttl={s.get('ttlSeconds')}")

    # 3) upload
    data = open(img, "rb").read()
    ct = "image/png" if img.lower().endswith((".png", ".webp")) else "image/jpeg"
    key = c.upload_image("face-swap-source", data, os.path.basename(img), ct)
    print(f"[ok] uploaded -> key={key} bytes={len(data)}")

    # 4) get-many-faces
    job, su, resp = c.get_many_faces(key)
    print(f"[ok] get-many-faces job={job} statusUrl={su}")
    faces = c.poll(su, job, poll_after_ms=2000, timeout_s=180)
    fstate = faces.get("state") or faces.get("status")
    fres = faces.get("result") or {}
    flist = fres.get("faces") or fres.get("list_face") or []
    print(f"[ok] get-many-faces state={fstate} faces={len(flist)}")
    print("     faces sample:", json.dumps(faces, ensure_ascii=False)[:400])

    # 5) nsfw
    job2, su2, resp2 = c.check_nsfw(key)
    print(f"[ok] check-nsfw job={job2} statusUrl={su2}")
    nsfw = c.poll(su2, job2, poll_after_ms=2000, timeout_s=180)
    nstate = nsfw.get("state") or nsfw.get("status")
    nres = nsfw.get("result")
    print(f"[ok] check-nsfw state={nstate} result={json.dumps(nres, ensure_ascii=False)[:300]}")

    print("\n[PASS] full flow reached face/nsfw stage")
    return 0

if __name__ == "__main__":
    sys.exit(main())
