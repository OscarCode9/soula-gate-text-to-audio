from typing import AsyncGenerator, Optional, Dict, Tuple
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
import gc
import hashlib
import os
from functools import lru_cache

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

# Cache de audio para evitar regenerar contenido idéntico
_audio_cache: Dict[str, Tuple[np.ndarray, float]] = {}  # hash -> (audio, timestamp)
_audio_cache_lock = threading.Lock()
_max_cache_size = 100  # Máximo número de audios en cache
_cache_ttl = 3600  # TTL de 1 hora para cache de audio

# Thread pool con más workers basado en CPU cores disponibles
cpu_count = os.cpu_count() or 4
optimal_workers = min(max(cpu_count, 4), 12)  # Entre 4 y 12 workers
audio_executor = ThreadPoolExecutor(max_workers=optimal_workers)
io_executor = ThreadPoolExecutor(max_workers=4)  # Executor separado para I/O

# Estadísticas de uso
_stats = defaultdict(int)
_stats_lock = threading.Lock()


def get_audio_cache_key(text: str, voice: str, speed: float, lang: str) -> str:
    """Generar clave única para cache de audio"""
    content = f"{text}:{voice}:{speed}:{lang}"
    return hashlib.md5(content.encode()).hexdigest()


def get_cached_audio(cache_key: str) -> Optional[np.ndarray]:
    """Obtener audio del cache si existe y es válido"""
    with _audio_cache_lock:
        if cache_key in _audio_cache:
            audio, timestamp = _audio_cache[cache_key]
            if time.time() - timestamp < _cache_ttl:
                # Mover al final para LRU
                _audio_cache[cache_key] = (audio, time.time())
                return audio
            else:
                # Eliminar entrada expirada
                del _audio_cache[cache_key]
    return None


def cache_audio(cache_key: str, audio: np.ndarray):
    """Guardar audio en cache con gestión de tamaño"""
    with _audio_cache_lock:
        # Limpiar cache si está lleno
        if len(_audio_cache) >= _max_cache_size:
            # Eliminar el 20% más antiguo
            items = list(_audio_cache.items())
            items.sort(key=lambda x: x[1][1])  # Ordenar por timestamp
            for key, _ in items[:_max_cache_size // 5]:
                del _audio_cache[key]
        
        _audio_cache[cache_key] = (audio, time.time())


def get_pipeline(lang_code: str = "a") -> KPipeline:
    """Obtener pipeline con cache por idioma"""
    global _pipeline_cache
    
    with _cache_lock:
        if lang_code not in _pipeline_cache:
            print(f"Creando nuevo pipeline para idioma: {lang_code}")
            _pipeline_cache[lang_code] = KPipeline(lang_code=lang_code)
            
            # Limpiar cache si hay demasiados pipelines (gestión de memoria)
            if len(_pipeline_cache) > 5:  # Aumentado de 3 a 5
                # Mantener solo los 5 más recientes
                oldest_lang = next(iter(_pipeline_cache))
                print(f"Eliminando pipeline más antiguo: {oldest_lang}")
                del _pipeline_cache[oldest_lang]
                gc.collect()  # Forzar garbage collection
        
        # Actualizar estadísticas
        with _stats_lock:
            _stats[f"pipeline_access_{lang_code}"] += 1
            
        return _pipeline_cache[lang_code]


# Pre-calentar pipelines más comunes al inicio
async def warmup_pipelines():
    """Pre-calentar pipelines comunes para reducir latencia inicial"""
    common_langs = ["a", "e"]  # Inglés y otros comunes
    for lang in common_langs:
        try:
            print(f"Pre-calentando pipeline {lang}...")
            pipeline = get_pipeline(lang)
            # Generar audio pequeño para inicializar completamente
            list(pipeline("Hi", voice="af_heart", speed=1.0))
            print(f"✓ Pipeline {lang} pre-calentado")
        except Exception as e:
            print(f"Error pre-calentando pipeline {lang}: {e}")


@lru_cache(maxsize=32)
def get_optimized_chunks(text: str, max_words: int) -> Tuple[str, ...]:
    """Versión optimizada y cacheada de división de texto"""
    return tuple(smart_text_split(text, max_words))


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
    """Función síncrona optimizada para generar audio de un chunk"""
    try:
        # Verificar cache primero
        cache_key = get_audio_cache_key(text_chunk, voice, speed, lang)
        cached_audio = get_cached_audio(cache_key)
        if cached_audio is not None:
            with _stats_lock:
                _stats["cache_hits"] += 1
            return cached_audio
        
        pipeline = get_pipeline(lang)
        generator = pipeline(text_chunk, voice=voice, speed=speed, split_pattern=r"\n+|[.!?]+\s+")
        audio_list = []
        for _, _, audio in generator:
            audio_list.append(audio)
        
        if audio_list:
            result = np.concatenate(audio_list)
            # Guardar en cache
            cache_audio(cache_key, result)
            
            # Actualizar estadísticas
            with _stats_lock:
                _stats["chunks_processed"] += 1
                _stats["total_samples"] += len(result)
                _stats["cache_misses"] += 1
            return result
        else:
            # Retornar silencio muy corto si no hay audio
            return np.zeros(int(24000 * 0.1), dtype=np.float32)
    except Exception as e:
        print(f"Error generando audio para chunk: {e}")
        # Retornar silencio en caso de error para evitar fallos completos
        return np.zeros(int(24000 * 0.1), dtype=np.float32)


# Función optimizada para escribir audio
def write_audio_to_bytes_optimized(audio: np.ndarray, format_type: str = "WAV") -> bytes:
    """Función optimizada para escribir audio a bytes"""
    buf = io.BytesIO()
    # Usar parámetros optimizados para mejor velocidad
    sf.write(buf, audio, 24000, format=format_type, subtype='PCM_16')  # 16-bit para menor tamaño
    return buf.getvalue()


@app.get("/")
async def root():
    return {"ok": True, "service": "kokoro-tts", "endpoints": ["POST /tts", "POST /tts/stream", "GET /stats", "GET /health"]}


@app.get("/health")
async def health_check():
    """Endpoint de salud del sistema mejorado"""
    try:
        # Verificar que al menos un pipeline funcione
        test_pipeline = get_pipeline("a")
        
        # Stats rápidas
        with _stats_lock:
            current_stats = dict(_stats)
        
        # Información del sistema
        cache_info = {
            "audio_cache_size": len(_audio_cache),
            "max_cache_size": _max_cache_size,
            "pipelines_loaded": len(_pipeline_cache),
            "thread_pool_workers": optimal_workers,
            "cache_hit_rate": (
                current_stats.get("cache_hits", 0) / 
                max(current_stats.get("cache_hits", 0) + current_stats.get("cache_misses", 0), 1) * 100
            )
        }
        
        return {
            "status": "healthy",
            "pipelines_available": len(_pipeline_cache),
            "thread_pool_active": not audio_executor._shutdown,
            "total_requests": current_stats.get("total_requests", 0),
            "success_rate": (
                current_stats.get("successful_requests", 0) / 
                max(current_stats.get("total_requests", 1), 1) * 100
            ),
            "cache_info": cache_info
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
        
        # Usar división de texto optimizada y cacheada
        text_chunks = get_optimized_chunks(req.text, req.max_chunk_words)
        
        if len(text_chunks) == 1:
            # Texto corto, procesamiento asíncrono directo
            loop = asyncio.get_event_loop()
            audio = await loop.run_in_executor(
                audio_executor,
                generate_audio_sync,
                req.text, req.voice, req.speed, req.lang
            )
        else:
            # Texto largo, procesamiento paralelo optimizado
            loop = asyncio.get_event_loop()
            
            # Semáforo dinámico basado en número de chunks
            max_concurrent = min(optimal_workers // 2, len(text_chunks), 6)
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def process_chunk_with_limit(chunk):
                async with semaphore:
                    return await loop.run_in_executor(
                        audio_executor, 
                        generate_audio_sync, 
                        chunk, req.voice, req.speed, req.lang
                    )
            
            # Procesar chunks con límite de concurrencia optimizado
            tasks = [process_chunk_with_limit(chunk) for chunk in text_chunks]
            audio_chunks = await asyncio.gather(*tasks)
            
            # Concatenar todos los chunks de audio
            audio = np.concatenate([chunk for chunk in audio_chunks if len(chunk) > 0])

        # Write WAV to bytes de forma asíncrona con executor optimizado
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            io_executor,  # Usar executor separado para I/O
            write_audio_to_bytes_optimized,
            audio
        )
        
        processing_time = time.time() - start_time
        
        # Actualizar estadísticas de rendimiento
        with _stats_lock:
            _stats["total_processing_time"] += processing_time
            _stats["successful_requests"] += 1
            _stats["avg_processing_time"] = _stats["total_processing_time"] / _stats["successful_requests"]
        
        print(f"TTS processing took {processing_time:.2f}s for {len(req.text)} chars ({len(text_chunks)} chunks)")
        
        return Response(content=data, media_type="audio/wav")
    except Exception as e:
        with _stats_lock:
            _stats["failed_requests"] += 1
        import traceback
        traceback.print_exc()  # Log to server console for debugging
        raise HTTPException(status_code=500, detail=f"Error de síntesis: {str(e)}")


def write_audio_to_bytes(audio: np.ndarray) -> bytes:
    """Función separada para escribir audio a bytes (para backward compatibility)"""
    return write_audio_to_bytes_optimized(audio)


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
        
        # Dividir el texto en chunks optimizados para streaming
        text_chunks = get_optimized_chunks(req.text, req.max_chunk_words)
        
        print(f"Streaming {len(text_chunks)} chunks for text of {len(req.text)} characters")
        
        # Buffer optimizado para pre-generar chunks
        loop = asyncio.get_event_loop()
        max_concurrent_stream = min(3, optimal_workers // 3)  # Dinámico basado en workers
        semaphore = asyncio.Semaphore(max_concurrent_stream)
        
        # Cola con tamaño optimizado
        chunk_queue = asyncio.Queue(maxsize=max_concurrent_stream + 1)
        
        async def chunk_producer():
            """Produce chunks de audio de forma asíncrona optimizada"""
            for i, chunk_text in enumerate(text_chunks):
                try:
                    async with semaphore:
                        audio = await loop.run_in_executor(
                            audio_executor,
                            generate_audio_sync,
                            chunk_text, req.voice, req.speed, req.lang
                        )
                        
                        # Convertir a WAV con executor optimizado
                        chunk_data = await loop.run_in_executor(
                            io_executor,
                            write_audio_to_bytes_optimized,
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
                # Timeout reducido para mejor responsividad
                item = await asyncio.wait_for(chunk_queue.get(), timeout=20.0)
                
                if item is None:  # Fin del stream
                    break
                
                chunk_index, chunk_data = item
                
                if chunk_data:  # Solo enviar si hay datos
                    chunk_count += 1
                    print(f"Sending chunk {chunk_index + 1}/{len(text_chunks)} ({len(chunk_data)} bytes)")
                    yield part("audio/wav", chunk_data)
                    
                    # Pausa optimizada para mejor fluidez
                    await asyncio.sleep(0.001)  # Reducido para mejor throughput
                
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
            if _stats["successful_streams"] > 0:
                _stats["avg_stream_time"] = _stats["total_stream_time"] / _stats["successful_streams"]
        
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


# Función de limpieza automática optimizada para gestión de memoria
async def cleanup_task():
    """Tarea de limpieza periódica optimizada para mejor rendimiento"""
    while True:
        try:
            await asyncio.sleep(180)  # Cada 3 minutos (más frecuente)
            
            with _stats_lock:
                total_requests = _stats.get("total_requests", 0)
            
            # Limpieza más agresiva y eficiente
            if total_requests > 0 and total_requests % 25 == 0:  # Cada 25 requests
                print("Ejecutando limpieza automática optimizada...")
                
                # Limpiar cache de audio expirado
                current_time = time.time()
                with _audio_cache_lock:
                    expired_keys = [
                        key for key, (_, timestamp) in _audio_cache.items()
                        if current_time - timestamp > _cache_ttl
                    ]
                    for key in expired_keys:
                        del _audio_cache[key]
                    
                    if expired_keys:
                        print(f"Eliminadas {len(expired_keys)} entradas de cache expiradas")
                
                # Limpiar cache de chunks de texto (LRU)
                if get_optimized_chunks.cache_info().currsize > 20:
                    get_optimized_chunks.cache_clear()
                    print("Cache de chunks de texto limpiado")
                
                # Garbage collection menos agresivo
                gc.collect()
                
                # Limpiar estadísticas detalladas pero mantener importantes
                with _stats_lock:
                    important_keys = [
                        "total_requests", "successful_requests", "failed_requests",
                        "stream_requests", "successful_streams", "failed_streams",
                        "chunks_processed", "total_samples", "cache_hits", "cache_misses",
                        "total_processing_time", "total_stream_time", "avg_processing_time", "avg_stream_time"
                    ]
                    # Mantener solo estadísticas importantes y recientes
                    temp_stats = {k: v for k, v in _stats.items() 
                                if any(imp in k for imp in important_keys)}
                    _stats.clear()
                    _stats.update(temp_stats)
                    
                print("Limpieza optimizada completada")
                
        except Exception as e:
            print(f"Error en tarea de limpieza: {e}")


# Endpoint para limpiar caches manualmente
@app.post("/admin/clear-cache")
async def clear_cache():
    """Endpoint para limpiar todos los caches manualmente"""
    try:
        with _audio_cache_lock:
            cache_size = len(_audio_cache)
            _audio_cache.clear()
        
        get_optimized_chunks.cache_clear()
        gc.collect()
        
        return {
            "success": True,
            "message": f"Cache limpiado: {cache_size} entradas de audio eliminadas"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Iniciar tareas de optimización al arranque
@app.on_event("startup")
async def startup_event():
    print("🚀 Iniciando Soulgate Kokoro TTS optimizado...")
    print(f"CPU cores detectados: {cpu_count}")
    print(f"Thread pool configurado con {optimal_workers} workers para audio")
    print(f"Thread pool I/O configurado con 4 workers")
    print(f"Cache de audio configurado: max {_max_cache_size} entradas, TTL {_cache_ttl}s")
    
    # Iniciar tarea de limpieza
    asyncio.create_task(cleanup_task())
    
    # Pre-calentar pipelines comunes en background
    asyncio.create_task(warmup_pipelines())


@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 Cerrando Soulgate Kokoro TTS...")
    audio_executor.shutdown(wait=True)
    io_executor.shutdown(wait=True)
    print("Thread pools cerrados correctamente")
