from typing import AsyncGenerator, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import io
import soundfile as sf
import numpy as np
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
import time

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
    chunk_size: int = Field(50, ge=10, le=200, description="Tamaño de chunk en palabras para streaming")
    max_chunk_words: int = Field(30, ge=5, le=100, description="Máximo de palabras por chunk de audio")


# Thread pool para procesamiento de audio
audio_executor = ThreadPoolExecutor(max_workers=2)


def smart_text_split(text: str, max_words: int = 30) -> list[str]:
    """
    Divide el texto en chunks más inteligentes:
    - Respeta oraciones cuando es posible
    - Divide por comas si la oración es muy larga
    - Mantiene chunks de tamaño razonable
    """
    # Primero dividir por oraciones
    sentences = re.split(r'[.!?]+\s+', text.strip())
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if not sentence.strip():
            continue
            
        words = sentence.split()
        
        # Si la oración es muy larga, dividirla por comas o por palabras
        if len(words) > max_words:
            # Intentar dividir por comas
            parts = re.split(r',\s+', sentence)
            for part in parts:
                part_words = part.split()
                if len(part_words) > max_words:
                    # Dividir por palabras si sigue siendo muy largo
                    for i in range(0, len(part_words), max_words):
                        chunk_words = part_words[i:i + max_words]
                        chunks.append(' '.join(chunk_words))
                else:
                    if current_chunk and len(current_chunk.split()) + len(part_words) > max_words:
                        chunks.append(current_chunk.strip())
                        current_chunk = part
                    else:
                        current_chunk = f"{current_chunk} {part}".strip()
        else:
            # Oración normal
            if current_chunk and len(current_chunk.split()) + len(words) > max_words:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk = f"{current_chunk} {sentence}".strip()
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return [chunk for chunk in chunks if chunk.strip()]


def generate_audio_sync(text_chunk: str, voice: str, speed: float, lang: str) -> np.ndarray:
    """Función síncrona para generar audio de un chunk"""
    pipeline = get_pipeline(lang)
    generator = pipeline(text_chunk, voice=voice, speed=speed, split_pattern=r"\n+|[.!?]+\s+")
    audio_list = []
    for _, _, audio in generator:
        audio_list.append(audio)
    
    if audio_list:
        return np.concatenate(audio_list)
    else:
        # Retornar silencio muy corto si no hay audio
        return np.zeros(int(24000 * 0.1), dtype=np.float32)


@app.get("/")
async def root():
    return {"ok": True, "service": "kokoro-tts", "endpoints": ["POST /tts", "POST /tts/stream", "GET /stats"]}


@app.get("/stats")
async def get_stats():
    """Endpoint para obtener estadísticas del sistema"""
    return {
        "pipeline_loaded": _pipeline is not None,
        "current_language": getattr(_pipeline, "_lang_code", None) if _pipeline else None,
        "thread_pool_workers": audio_executor._max_workers,
        "default_chunk_size": 30,
        "recommended_chunk_sizes": {
            "short_text": "20-30 words",
            "medium_text": "25-35 words", 
            "long_text": "15-25 words",
            "streaming": "10-20 words"
        }
    }


@app.post("/tts")
async def tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")

    try:
        start_time = time.time()
        
        # Para textos largos, usar procesamiento paralelo
        text_chunks = smart_text_split(req.text, req.max_chunk_words)
        
        if len(text_chunks) == 1:
            # Texto corto, procesamiento directo
            pipeline = get_pipeline(req.lang)
            generator = pipeline(req.text, voice=req.voice, speed=req.speed, split_pattern=r"\n+|[.!?]+\s+")
            audio_list = []
            for _, _, audio in generator:
                audio_list.append(audio)
            if not audio_list:
                raise RuntimeError("No se generó audio")
            audio = np.concatenate(audio_list)
        else:
            # Texto largo, procesamiento paralelo
            loop = asyncio.get_event_loop()
            
            # Procesar chunks en paralelo
            tasks = []
            for chunk in text_chunks:
                task = loop.run_in_executor(
                    audio_executor, 
                    generate_audio_sync, 
                    chunk, req.voice, req.speed, req.lang
                )
                tasks.append(task)
            
            # Esperar a que todos los chunks estén listos
            audio_chunks = await asyncio.gather(*tasks)
            
            # Concatenar todos los chunks de audio
            audio = np.concatenate(audio_chunks)

        # Write WAV to bytes
        buf = io.BytesIO()
        sf.write(buf, audio, 24000, format="WAV")
        data = buf.getvalue()
        
        processing_time = time.time() - start_time
        print(f"TTS processing took {processing_time:.2f}s for {len(req.text)} chars ({len(text_chunks)} chunks)")
        
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
        start_time = time.time()
        
        # Dividir el texto en chunks más pequeños para mejor streaming
        text_chunks = smart_text_split(req.text, req.max_chunk_words)
        
        print(f"Streaming {len(text_chunks)} chunks for text of {len(req.text)} characters")
        
        # Buffer para pre-generar el siguiente chunk mientras se envía el actual
        loop = asyncio.get_event_loop()
        
        # Generar el primer chunk
        if text_chunks:
            next_task = loop.run_in_executor(
                audio_executor,
                generate_audio_sync,
                text_chunks[0], req.voice, req.speed, req.lang
            )
            
            for i, chunk_text in enumerate(text_chunks):
                chunk_start = time.time()
                
                # Esperar el audio del chunk actual
                audio = await next_task
                
                # Comenzar a generar el siguiente chunk en paralelo (si existe)
                if i + 1 < len(text_chunks):
                    next_task = loop.run_in_executor(
                        audio_executor,
                        generate_audio_sync,
                        text_chunks[i + 1], req.voice, req.speed, req.lang
                    )
                
                # Convertir a WAV y enviar
                buf = io.BytesIO()
                sf.write(buf, audio, 24000, format="WAV")
                chunk_data = buf.getvalue()
                
                chunk_time = time.time() - chunk_start
                print(f"Chunk {i+1}/{len(text_chunks)} processed in {chunk_time:.2f}s ({len(chunk_data)} bytes)")
                
                yield part("audio/wav", chunk_data)
                
                # Pequeña pausa para hacer el streaming más natural
                await asyncio.sleep(0.01)
        
        # Close the multipart with terminating boundary
        total_time = time.time() - start_time
        print(f"Total streaming time: {total_time:.2f}s")
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
