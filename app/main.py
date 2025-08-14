from typing import AsyncGenerator, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import io
import soundfile as sf
import numpy as np

# Kokoro pipeline
from kokoro import KPipeline

app = FastAPI(title="Soulgate Kokoro TTS", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Lazy singleton for the pipeline
_pipeline: Optional[KPipeline] = None


def get_pipeline(lang_code: str = "a") -> KPipeline:
    global _pipeline
    # Reuse single pipeline per process; recreate if language changes
    # Kokoro voices are language-specific; simplest approach: new pipeline if lang differs
    if _pipeline is None or getattr(_pipeline, "_lang_code", None) != lang_code:
        _pipeline = KPipeline(lang_code=lang_code)
        setattr(_pipeline, "_lang_code", lang_code)
    return _pipeline


class TTSRequest(BaseModel):
    text: str = Field(..., description="Texto a sintetizar")
    lang: str = Field("a", description="Código de idioma Kokoro: a,b,e,f,h,i,j,p,z")
    voice: str = Field("af_heart", description="Nombre de voz, p.ej. af_heart")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Velocidad de habla")


@app.get("/")
async def root():
    return {"ok": True, "service": "kokoro-tts", "endpoints": ["POST /tts", "POST /tts/stream"]}


@app.post("/tts")
async def tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")

    try:
        pipeline = get_pipeline(req.lang)
        # Generate audio chunks (one per sentence by default split pattern) and concatenate
        generator = pipeline(req.text, voice=req.voice, speed=req.speed, split_pattern=r"\n+|[.!?]+\s+")
        audio_list = []
        for _, _, audio in generator:
            # audio is float32 numpy array, 24000 Hz
            audio_list.append(audio)
        if not audio_list:
            raise RuntimeError("No se generó audio")
        audio = np.concatenate(audio_list)

        # Write WAV to bytes
        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format="WAV")
        data = buf.getvalue()
        return Response(content=data, media_type="audio/wav")
    except Exception as e:
        import traceback
        traceback.print_exc()  # Log to server console for debugging
        raise HTTPException(status_code=500, detail=f"Error de síntesis: {str(e)}")


BOUNDARY = "--frame"


def part(content_type: str, data: bytes) -> bytes:
    headers = (
        f"{BOUNDARY}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(data)}\r\n\r\n"
    ).encode("utf-8")
    return headers + data + b"\r\n"


async def wav_stream(req: TTSRequest) -> AsyncGenerator[bytes, None]:
    try:
        pipeline = get_pipeline(req.lang)
        generator = pipeline(req.text, voice=req.voice, speed=req.speed, split_pattern=r"\n+|[.!?]+\s+")
        for _, _, audio in generator:
            # Build a tiny per-sentence WAV
            buf = io.BytesIO()
            sf.write(buf, audio, 24000, format="WAV")
            yield part("audio/wav", buf.getvalue())
        # Close the multipart with terminating boundary
        yield (f"{BOUNDARY}--\r\n").encode("utf-8")
    except Exception as e:
        # On error, send a text/plain part with the error message
        err = f"Error: {e}".encode("utf-8")
        yield part("text/plain; charset=utf-8", err)
        yield (f"{BOUNDARY}--\r\n").encode("utf-8")


@app.post("/tts/stream")
async def tts_stream(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")
    media_type = f"multipart/mixed; boundary={BOUNDARY[2:]}"  # boundary without the leading dashes
    return StreamingResponse(wav_stream(req), media_type=media_type)
