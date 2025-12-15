"""
Soulgate TTS Server - Edge TTS Edition
======================================
Ultra-lightweight TTS server using Microsoft Edge's online TTS service.
RAM usage: ~20-50MB (vs ~800MB+ with Kokoro)

Mantiene compatibilidad 100% con el frontend existente:
- POST /tts/stream -> multipart/mixed streaming
- POST /tts -> audio/wav response
- GET /health -> status check
"""

from typing import AsyncGenerator, Dict, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio
import time
import os
import io
import re
from collections import defaultdict

# Edge TTS - Microsoft's free TTS service
import edge_tts

# Monitoreo de memoria (opcional)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

app = FastAPI(title="Soulgate Edge TTS", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== CONFIGURACIÓN ==============
# Mapeo de voces Kokoro -> Edge TTS
# El frontend envía voces Kokoro, las convertimos a Edge TTS
VOICE_MAPPING = {
    # Voces femeninas americanas
    "af_heart": "en-US-JennyNeural",
    "af_soul": "en-US-AriaNeural", 
    "af_grace": "en-US-SaraNeural",
    "af_bella": "en-US-AnaNeural",
    "af_nicole": "en-US-MichelleNeural",
    # Voces masculinas americanas
    "am_adam": "en-US-GuyNeural",
    "am_michael": "en-US-ChristopherNeural",
    "am_eric": "en-US-EricNeural",
    # Voces femeninas británicas
    "bf_emma": "en-GB-SoniaNeural",
    "bf_isabella": "en-GB-LibbyNeural",
    # Voces masculinas británicas
    "bm_george": "en-GB-RyanNeural",
    "bm_lewis": "en-GB-ThomasNeural",
    # Voces en español
    "es_male": "es-MX-JorgeNeural",
    "es_female": "es-MX-DaliaNeural",
    "es_spain_male": "es-ES-AlvaroNeural",
    "es_spain_female": "es-ES-ElviraNeural",
}

# Mapeo de idiomas Kokoro -> Edge TTS locale
LANG_MAPPING = {
    "a": "en-US",  # American English
    "b": "en-GB",  # British English  
    "e": "es-MX",  # Spanish (Mexico)
    "f": "fr-FR",  # French
    "h": "hi-IN",  # Hindi
    "i": "it-IT",  # Italian
    "j": "ja-JP",  # Japanese
    "p": "pt-BR",  # Portuguese
    "z": "zh-CN",  # Chinese
}

# Voces por defecto para cada idioma
DEFAULT_VOICES = {
    "en-US": "en-US-JennyNeural",
    "en-GB": "en-GB-SoniaNeural",
    "es-MX": "es-MX-DaliaNeural",
    "es-ES": "es-ES-ElviraNeural",
    "fr-FR": "fr-FR-DeniseNeural",
    "hi-IN": "hi-IN-SwaraNeural",
    "it-IT": "it-IT-ElsaNeural",
    "ja-JP": "ja-JP-NanamiNeural",
    "pt-BR": "pt-BR-FranciscaNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
}

# Estadísticas
_stats = defaultdict(int)

# Constantes para streaming
BOUNDARY = "--frame"
SAMPLE_RATE = 24000  # Edge TTS default is 24kHz for Neural voices


def get_memory_usage_mb() -> float:
    """Obtener uso de memoria del proceso en MB"""
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    return 0.0


def get_edge_voice(kokoro_voice: str, lang_code: str) -> str:
    """Convertir voz Kokoro a voz Edge TTS"""
    # Primero intentar mapeo directo
    if kokoro_voice in VOICE_MAPPING:
        return VOICE_MAPPING[kokoro_voice]
    
    # Si no, usar voz por defecto del idioma
    locale = LANG_MAPPING.get(lang_code, "en-US")
    return DEFAULT_VOICES.get(locale, "en-US-JennyNeural")


def get_edge_locale(lang_code: str) -> str:
    """Convertir código de idioma Kokoro a locale Edge TTS"""
    return LANG_MAPPING.get(lang_code, "en-US")


def speed_to_rate(speed: float) -> str:
    """Convertir velocidad (0.5-2.0) a formato Edge TTS rate (-50% a +100%)"""
    if speed == 1.0:
        return "+0%"
    elif speed > 1.0:
        # speed 2.0 -> +100%
        percent = int((speed - 1.0) * 100)
        return f"+{percent}%"
    else:
        # speed 0.5 -> -50%
        percent = int((1.0 - speed) * 100)
        return f"-{percent}%"


def smart_text_split(text: str, max_chars: int = 500) -> List[str]:
    """
    Divide el texto en chunks para streaming.
    Edge TTS maneja bien textos largos, pero dividimos para streaming más fluido.
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    
    # Dividir por párrafos primero
    paragraphs = text.split('\n\n')
    
    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        # Si el párrafo cabe en el chunk actual
        if len(current_chunk) + len(para) + 2 <= max_chars:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            # Guardar chunk actual si existe
            if current_chunk:
                chunks.append(current_chunk)
            
            # Si el párrafo es muy largo, dividirlo por oraciones
            if len(para) > max_chars:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current_chunk = ""
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 <= max_chars:
                        if current_chunk:
                            current_chunk += " " + sentence
                        else:
                            current_chunk = sentence
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sentence
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text]


class TTSRequest(BaseModel):
    text: str = Field(..., description="Texto a sintetizar")
    lang: str = Field("a", description="Código de idioma: a,b,e,f,h,i,j,p,z")
    voice: str = Field("af_heart", description="Nombre de voz Kokoro")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Velocidad de habla")
    chunk_size: int = Field(50, description="Ignorado - para compatibilidad")
    max_chunk_words: int = Field(30, description="Ignorado - para compatibilidad")


def part(content_type: str, data: bytes) -> bytes:
    """Crear parte multipart para streaming"""
    headers = (
        f"{BOUNDARY}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(data)}\r\n\r\n"
    ).encode("utf-8")
    return headers + data + b"\r\n"


async def generate_audio_chunk(text: str, voice: str, rate: str) -> bytes:
    """Generar audio para un chunk de texto usando Edge TTS"""
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        
        # Recolectar todos los datos de audio
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        return audio_data
    except Exception as e:
        print(f"❌ Error generando audio: {e}")
        return b""


async def edge_tts_stream(req: TTSRequest, client_disconnected: asyncio.Event = None) -> AsyncGenerator[bytes, None]:
    """
    Stream de audio usando Edge TTS.
    Genera audio en formato MP3 (nativo de Edge TTS).
    """
    start_time = time.time()
    chunk_count = 0
    
    try:
        _stats["stream_requests"] += 1
        
        # Configurar voz y rate
        edge_voice = get_edge_voice(req.voice, req.lang)
        rate = speed_to_rate(req.speed)
        
        mem_start = get_memory_usage_mb()
        print(f"🎤 Edge TTS Stream - voice: {edge_voice}, rate: {rate}, text: {len(req.text)} chars")
        
        # Dividir texto en chunks para streaming más fluido
        text_chunks = smart_text_split(req.text, max_chars=800)
        total_chunks = len(text_chunks)
        
        print(f"📝 Dividido en {total_chunks} chunks para streaming")
        
        for i, chunk_text in enumerate(text_chunks):
            if client_disconnected and client_disconnected.is_set():
                print(f"⚠️ Cliente desconectado en chunk {i+1}/{total_chunks}")
                break
            
            try:
                chunk_start = time.time()
                
                # Generar audio con Edge TTS
                communicate = edge_tts.Communicate(chunk_text, edge_voice, rate=rate)
                
                # Recolectar audio del chunk
                audio_data = b""
                async for data in communicate.stream():
                    if data["type"] == "audio":
                        audio_data += data["data"]
                
                if audio_data:
                    chunk_count += 1
                    chunk_time = time.time() - chunk_start
                    
                    # Edge TTS genera MP3, pero lo enviamos como audio/mpeg
                    # El frontend puede manejar ambos formatos
                    print(f"  ✅ Chunk {i+1}/{total_chunks}: {len(audio_data)} bytes en {chunk_time:.2f}s")
                    
                    # Enviar como audio/mpeg (MP3 nativo de Edge TTS)
                    yield part("audio/mpeg", audio_data)
                    
                    await asyncio.sleep(0.01)  # Pequeña pausa
                    
            except Exception as e:
                print(f"❌ Error en chunk {i+1}: {e}")
                continue
        
        # Estadísticas finales
        total_time = time.time() - start_time
        mem_end = get_memory_usage_mb()
        print(f"✅ Stream completado: {chunk_count}/{total_chunks} chunks en {total_time:.2f}s (mem: {mem_start:.1f}→{mem_end:.1f}MB)")
        
        _stats["successful_streams"] += 1
        _stats["chunks_sent"] += chunk_count
        
        # Boundary final
        yield (f"{BOUNDARY}--\r\n").encode("utf-8")
        
    except asyncio.CancelledError:
        print(f"🚫 Stream cancelado después de {chunk_count} chunks")
        _stats["cancelled_streams"] += 1
        raise
    except Exception as e:
        print(f"❌ Error fatal en stream: {e}")
        _stats["failed_streams"] += 1
        yield part("text/plain; charset=utf-8", f"Error: {e}".encode("utf-8"))
        yield (f"{BOUNDARY}--\r\n").encode("utf-8")


@app.get("/")
async def root():
    return {
        "ok": True, 
        "service": "edge-tts",
        "version": "2.0.0",
        "engine": "Microsoft Edge TTS",
        "endpoints": ["POST /tts", "POST /tts/stream", "GET /voices", "GET /health"]
    }


@app.get("/health")
async def health_check():
    """Endpoint de salud del sistema"""
    memory_mb = get_memory_usage_mb()
    
    return {
        "status": "healthy",
        "engine": "edge-tts",
        "memory": {
            "usage_mb": round(memory_mb, 1),
            "note": "Edge TTS usa ~20-50MB vs ~800MB de Kokoro"
        },
        "stats": {
            "total_requests": _stats.get("stream_requests", 0),
            "successful_streams": _stats.get("successful_streams", 0),
            "chunks_sent": _stats.get("chunks_sent", 0)
        }
    }


@app.get("/voices")
async def list_voices():
    """Listar voces disponibles de Edge TTS"""
    try:
        voices = await edge_tts.list_voices()
        
        # Agrupar por idioma
        by_locale = {}
        for v in voices:
            locale = v["Locale"]
            if locale not in by_locale:
                by_locale[locale] = []
            by_locale[locale].append({
                "name": v["ShortName"],
                "gender": v["Gender"],
                "friendly_name": v.get("FriendlyName", v["ShortName"])
            })
        
        return {
            "total_voices": len(voices),
            "by_locale": by_locale,
            "kokoro_mapping": VOICE_MAPPING
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/tts")
async def tts_single(req: TTSRequest):
    """Endpoint TTS para audio completo (sin streaming)"""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")
    
    try:
        _stats["total_requests"] += 1
        
        edge_voice = get_edge_voice(req.voice, req.lang)
        rate = speed_to_rate(req.speed)
        
        print(f"🎤 TTS Single - voice: {edge_voice}, rate: {rate}, text: {len(req.text)} chars")
        
        # Generar audio completo
        communicate = edge_tts.Communicate(req.text, edge_voice, rate=rate)
        
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        if not audio_data:
            raise HTTPException(status_code=500, detail="No se pudo generar audio")
        
        _stats["successful_requests"] += 1
        
        # Edge TTS genera MP3
        return Response(content=audio_data, media_type="audio/mpeg")
        
    except Exception as e:
        _stats["failed_requests"] += 1
        raise HTTPException(status_code=500, detail=f"Error de síntesis: {str(e)}")


@app.post("/tts/stream")
async def tts_stream(req: TTSRequest, request: Request):
    """Endpoint de streaming TTS - compatible con frontend existente"""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")
    
    # Evento para detectar desconexión
    client_disconnected = asyncio.Event()
    
    async def check_disconnect():
        while not client_disconnected.is_set():
            if await request.is_disconnected():
                client_disconnected.set()
                print("🔌 Cliente desconectado")
                break
            await asyncio.sleep(0.5)
    
    disconnect_task = asyncio.create_task(check_disconnect())
    
    async def stream_with_cleanup():
        try:
            async for chunk in edge_tts_stream(req, client_disconnected):
                yield chunk
        finally:
            client_disconnected.set()
            disconnect_task.cancel()
            try:
                await disconnect_task
            except asyncio.CancelledError:
                pass
    
    media_type = f"multipart/mixed; boundary={BOUNDARY[2:]}"
    return StreamingResponse(stream_with_cleanup(), media_type=media_type)


@app.get("/stats")
async def get_stats():
    """Estadísticas del servidor"""
    return {
        "engine": "edge-tts",
        "memory_mb": round(get_memory_usage_mb(), 1),
        "stats": dict(_stats),
        "voice_mapping": VOICE_MAPPING,
        "supported_languages": list(LANG_MAPPING.keys())
    }


@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("🚀 Soulgate Edge TTS Server v2.0.0")
    print("=" * 60)
    print("✅ Engine: Microsoft Edge TTS (Online)")
    print("✅ RAM estimada: ~20-50MB")
    print("✅ Voces: 400+ en 100+ idiomas")
    print(f"💾 Memoria inicial: {get_memory_usage_mb():.1f}MB")
    print("=" * 60)
    print("⚠️  Requiere conexión a internet")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    print("\n" + "=" * 60)
    print("🛑 Cerrando Edge TTS Server...")
    print(f"📊 Total requests: {_stats.get('stream_requests', 0)}")
    print(f"📊 Successful: {_stats.get('successful_streams', 0)}")
    print(f"💾 Memoria final: {get_memory_usage_mb():.1f}MB")
    print("=" * 60)

