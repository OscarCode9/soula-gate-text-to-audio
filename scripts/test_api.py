#!/usr/bin/env python3
"""
Script de prueba para la API de Kokoro TTS.
- GET /
- POST /tts -> guarda out.wav
- POST /tts/stream -> guarda chunks stream_0001.wav, etc.

Requiere que el servidor esté corriendo en http://127.0.0.1:8000
"""
import json
import os
import sys
import uuid
from urllib import request

BASE = os.environ.get("TTS_BASE", "http://127.0.0.1:8010")
TEXT = os.environ.get("TTS_TEXT", "Hello world. This is a quick streaming test.")
LANG = os.environ.get("TTS_LANG", "a")  # 'a' English (fastest to bootstrap)
VOICE = os.environ.get("TTS_VOICE", "af_heart")
SPEED = float(os.environ.get("TTS_SPEED", "1.0"))


def http_get(path: str):
    with request.urlopen(f"{BASE}{path}") as r:
        print("GET", path, r.status, r.headers.get("content-type"))
        return r.read()


def http_post_json(path: str, payload: dict):
    data = json.dumps(payload).encode()
    req = request.Request(
        f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    return request.urlopen(req)


def save_bytes(path: str, data: bytes):
    with open(path, "wb") as f:
        f.write(data)
    print("saved", path, len(data), "bytes")


def parse_multipart_stream(raw: bytes, boundary: bytes):
    # Simple parser for multipart/mixed; splits on b"--<boundary>\r\n"
    marker = b"--" + boundary
    parts = []
    for block in raw.split(marker):
        block = block.strip()
        if not block or block == b"--":
            continue
        # Separate headers and body
        if b"\r\n\r\n" not in block:
            continue
        headers_raw, body = block.split(b"\r\n\r\n", 1)
        headers = {}
        for line in headers_raw.split(b"\r\n"):
            if b":" in line:
                k, v = line.split(b":", 1)
                headers[k.strip().lower()] = v.strip()
        parts.append((headers, body.rstrip(b"\r\n")))
    return parts


def main():
    # 1) Root
    root = http_get("/")
    print("root:", root.decode(errors="ignore"))

    # 2) /tts no streaming
    payload = {"text": TEXT, "lang": LANG, "voice": VOICE, "speed": SPEED}
    with http_post_json("/tts", payload) as r:
        print("POST /tts", r.status, r.headers.get("content-type"))
        wav = r.read()
        save_bytes("out.wav", wav)

    # 3) /tts/stream multipart
    req = request.Request(
        f"{BASE}/tts/stream",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "multipart/mixed",
        },
    )
    with request.urlopen(req) as r:
        ctype = r.headers.get("content-type", "")
        print("POST /tts/stream", r.status, ctype)
        # Extract boundary
        boundary = None
        if "boundary=" in ctype:
            boundary = ctype.split("boundary=", 1)[1].strip().encode()
        raw = r.read()
        if boundary:
            parts = parse_multipart_stream(raw, boundary)
            for i, (headers, body) in enumerate(parts, start=1):
                kind = headers.get(b"content-type", b"?").decode()
                fname = f"stream_{i:04d}.wav" if kind.startswith("audio/wav") else f"stream_{i:04d}.bin"
                save_bytes(fname, body)
        else:
            save_bytes("stream_raw.bin", raw)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
