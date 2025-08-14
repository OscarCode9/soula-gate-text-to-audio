from typing import AsyncGenerator, Optional, Dict
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
import threading
from collections import defaultdict
import queue
import gc

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

# Cache de pipelines por idioma para evitar recargas
_pipeline_cache: Dict[str, KPipeline] = {}
_cache_lock = threading.Lock()

# Thread pool con más workers para mejor concurrencia
audio_executor = ThreadPoolExecutor(max_workers=4)

# Estadísticas de uso
_stats = defaultdict(int)
_stats_lock = threading.Lock()


def get_pipeline(lang_code: str = "a") -> KPipeline:
    """Obtener pipeline con cache por idioma"""
    global _pipeline_cache
    
    with _cache_lock:
        if lang_code not in _pipeline_cache:
            print(f"Creando nuevo pipeline para idioma: {lang_code}")
            _pipeline_cache[lang_code] = KPipeline(lang_code=lang_code)
            
            # Limpiar cache si hay demasiados pipelines (gestión de memoria)
            if len(_pipeline_cache) > 3:
                # Mantener solo los 3 más recientes
                oldest_lang = next(iter(_pipeline_cache))
                print(f"Eliminando pipeline más antiguo: {oldest_lang}")
                del _pipeline_cache[oldest_lang]
                gc.collect()  # Forzar garbage collection
        
        # Actualizar estadísticas
        with _stats_lock:
            _stats[f"pipeline_access_{lang_code}"] += 1
            
        return _pipeline_cache[lang_code]


class TTSRequest(BaseModel):
    text: str = Field(..., description="Texto a sintetizar")
    lang: str = Field("a", description="Código de idioma Kokoro: a,b,e,f,h,i,j,p,z")
    voice: str = Field("af_heart", description="Nombre de voz, p.ej. af_heart")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Velocidad de habla")
    chunk_size: int = Field(50, ge=10, le=200, description="Tamaño de chunk en palabras para streaming")
    max_chunk_words: int = Field(30, ge=5, le=100, description="Máximo de palabras por chunk de audio")


# Thread pool para procesamiento de audio - eliminado, ya está definido arriba


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
    try:
        pipeline = get_pipeline(lang)
        generator = pipeline(text_chunk, voice=voice, speed=speed, split_pattern=r"\n+|[.!?]+\s+")
        audio_list = []
        for _, _, audio in generator:
            audio_list.append(audio)
        
        if audio_list:
            result = np.concatenate(audio_list)
            # Actualizar estadísticas
            with _stats_lock:
                _stats["chunks_processed"] += 1
                _stats["total_samples"] += len(result)
            return result
        else:
            # Retornar silencio muy corto si no hay audio
            return np.zeros(int(24000 * 0.1), dtype=np.float32)
    except Exception as e:
        print(f"Error generando audio para chunk: {e}")
        # Retornar silencio en caso de error para evitar fallos completos
        return np.zeros(int(24000 * 0.1), dtype=np.float32)


@app.get("/")
async def root():
    return {"ok": True, "service": "kokoro-tts", "endpoints": ["POST /tts", "POST /tts/stream", "GET /stats", "GET /health"]}


@app.get("/health")
async def health_check():
    """Endpoint de salud del sistema"""
    try:
        # Verificar que al menos un pipeline funcione
        test_pipeline = get_pipeline("a")
        
        # Stats rápidas
        with _stats_lock:
            current_stats = dict(_stats)
        
        return {
            "status": "healthy",
            "pipelines_available": len(_pipeline_cache),
            "thread_pool_active": not audio_executor._shutdown,
            "total_requests": current_stats.get("total_requests", 0),
            "success_rate": (
                current_stats.get("successful_requests", 0) / 
                max(current_stats.get("total_requests", 1), 1) * 100
            )
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/stats")
async def get_stats():
    """Endpoint para obtener estadísticas del sistema"""
    with _stats_lock:
        current_stats = dict(_stats)
    
    return {
        "pipelines_loaded": len(_pipeline_cache),
        "loaded_languages": list(_pipeline_cache.keys()),
        "thread_pool_workers": audio_executor._max_workers,
        "processing_stats": current_stats,
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
        
        # Actualizar estadísticas
        with _stats_lock:
            _stats["total_requests"] += 1
            _stats[f"requests_lang_{req.lang}"] += 1
        
        # Para textos largos, usar procesamiento paralelo
        text_chunks = smart_text_split(req.text, req.max_chunk_words)
        
        if len(text_chunks) == 1:
            # Texto corto, procesamiento asíncrono directo
            loop = asyncio.get_event_loop()
            audio = await loop.run_in_executor(
                audio_executor,
                generate_audio_sync,
                req.text, req.voice, req.speed, req.lang
            )
        else:
            # Texto largo, procesamiento paralelo con límite de concurrencia
            loop = asyncio.get_event_loop()
            
            # Limitar concurrencia para evitar sobrecarga
            semaphore = asyncio.Semaphore(3)  # Máximo 3 chunks en paralelo
            
            async def process_chunk_with_limit(chunk):
                async with semaphore:
                    return await loop.run_in_executor(
                        audio_executor, 
                        generate_audio_sync, 
                        chunk, req.voice, req.speed, req.lang
                    )
            
            # Procesar chunks con límite de concurrencia
            tasks = [process_chunk_with_limit(chunk) for chunk in text_chunks]
            audio_chunks = await asyncio.gather(*tasks)
            
            # Concatenar todos los chunks de audio
            audio = np.concatenate([chunk for chunk in audio_chunks if len(chunk) > 0])

        # Write WAV to bytes de forma asíncrona
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,  # Default executor para I/O
            lambda: write_audio_to_bytes(audio)
        )
        
        processing_time = time.time() - start_time
        
        # Actualizar estadísticas de rendimiento
        with _stats_lock:
            _stats["total_processing_time"] += processing_time
            _stats["successful_requests"] += 1
        
        print(f"TTS processing took {processing_time:.2f}s for {len(req.text)} chars ({len(text_chunks)} chunks)")
        
        return Response(content=data, media_type="audio/wav")
    except Exception as e:
        with _stats_lock:
            _stats["failed_requests"] += 1
        import traceback
        traceback.print_exc()  # Log to server console for debugging
        raise HTTPException(status_code=500, detail=f"Error de síntesis: {str(e)}")


def write_audio_to_bytes(audio: np.ndarray) -> bytes:
    """Función separada para escribir audio a bytes (para executor)"""
    buf = io.BytesIO()
    sf.write(buf, audio, 24000, format="WAV")
    return buf.getvalue()


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
        
        # Actualizar estadísticas
        with _stats_lock:
            _stats["stream_requests"] += 1
        
        # Dividir el texto en chunks más pequeños para mejor streaming
        text_chunks = smart_text_split(req.text, req.max_chunk_words)
        
        print(f"Streaming {len(text_chunks)} chunks for text of {len(req.text)} characters")
        
        # Buffer para pre-generar chunks con límite de concurrencia
        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(2)  # Máximo 2 chunks en proceso simultáneo
        
        # Cola para manejar chunks de forma ordenada
        chunk_queue = asyncio.Queue(maxsize=3)  # Buffer de máximo 3 chunks
        
        async def chunk_producer():
            """Produce chunks de audio de forma asíncrona"""
            for i, chunk_text in enumerate(text_chunks):
                try:
                    async with semaphore:
                        audio = await loop.run_in_executor(
                            audio_executor,
                            generate_audio_sync,
                            chunk_text, req.voice, req.speed, req.lang
                        )
                        
                        # Convertir a WAV
                        chunk_data = await loop.run_in_executor(
                            None,
                            write_audio_to_bytes,
                            audio
                        )
                        
                        await chunk_queue.put((i, chunk_data))
                except Exception as e:
                    print(f"Error procesando chunk {i}: {e}")
                    # Poner chunk vacío para mantener el orden
                    await chunk_queue.put((i, b''))
            
            # Señal de fin
            await chunk_queue.put(None)
        
        # Iniciar productor
        producer_task = asyncio.create_task(chunk_producer())
        
        chunk_count = 0
        while True:
            try:
                # Esperar el siguiente chunk con timeout
                item = await asyncio.wait_for(chunk_queue.get(), timeout=30.0)
                
                if item is None:  # Fin del stream
                    break
                
                chunk_index, chunk_data = item
                
                if chunk_data:  # Solo enviar si hay datos
                    chunk_count += 1
                    print(f"Sending chunk {chunk_index + 1}/{len(text_chunks)} ({len(chunk_data)} bytes)")
                    yield part("audio/wav", chunk_data)
                    
                    # Pausa más pequeña para mejor fluidez
                    await asyncio.sleep(0.005)
                
            except asyncio.TimeoutError:
                print("Timeout esperando chunk, cerrando stream")
                break
            except Exception as e:
                print(f"Error en streaming: {e}")
                break
        
        # Esperar que termine el productor
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass
        
        # Close the multipart with terminating boundary
        total_time = time.time() - start_time
        print(f"Total streaming time: {total_time:.2f}s, chunks sent: {chunk_count}")
        
        # Actualizar estadísticas
        with _stats_lock:
            _stats["successful_streams"] += 1
            _stats["total_stream_time"] += total_time
        
        yield (f"{BOUNDARY}--\r\n").encode("utf-8")
        
    except Exception as e:
        # Actualizar estadísticas de error
        with _stats_lock:
            _stats["failed_streams"] += 1
        
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


# Función de limpieza automática para gestión de memoria
async def cleanup_task():
    """Tarea de limpieza periódica para optimizar memoria"""
    while True:
        try:
            await asyncio.sleep(300)  # Cada 5 minutos
            
            with _stats_lock:
                total_requests = _stats.get("total_requests", 0)
            
            # Si hay muchas peticiones, hacer limpieza
            if total_requests > 0 and total_requests % 50 == 0:
                print("Ejecutando limpieza automática de memoria...")
                gc.collect()
                
                # Limpiar estadísticas muy antiguas (mantener solo contadores principales)
                with _stats_lock:
                    important_keys = [
                        "total_requests", "successful_requests", "failed_requests",
                        "stream_requests", "successful_streams", "failed_streams",
                        "chunks_processed", "total_samples"
                    ]
                    # Mantener solo estadísticas importantes
                    temp_stats = {k: v for k, v in _stats.items() if any(imp in k for imp in important_keys)}
                    _stats.clear()
                    _stats.update(temp_stats)
                    
                print("Limpieza completada")
                
        except Exception as e:
            print(f"Error en tarea de limpieza: {e}")


# Iniciar tarea de limpieza al arranque
@app.on_event("startup")
async def startup_event():
    print("🚀 Iniciando Soulgate Kokoro TTS...")
    print(f"Thread pool configurado con {audio_executor._max_workers} workers")
    asyncio.create_task(cleanup_task())


@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 Cerrando Soulgate Kokoro TTS...")
    audio_executor.shutdown(wait=True)
    print("Thread pool cerrado correctamente")
