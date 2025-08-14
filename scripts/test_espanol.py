#!/usr/bin/env python3
"""
Script de prueba específico para ESPAÑOL
Configurado para generar audio en español con voz femenina
"""
import json
import urllib.request
import time

BASE = "http://127.0.0.1:8010"

def test_spanish_tts():
    """Prueba TTS en español"""
    
    # Configuración para ESPAÑOL
    payload = {
        "text": "Hola, este es un ejemplo de síntesis de voz en español. ¿Cómo te suena?",
        "lang": "e",        # 'e' = Español
        "voice": "af_heart", # Voz femenina
        "speed": 1.0
    }
    
    print(f"🇪🇸 Generando audio en ESPAÑOL...")
    print(f"📝 Texto: {payload['text']}")
    print(f"🎤 Voz: {payload['voice']}")
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/tts", 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"✅ Respuesta: {r.status} {r.headers.get('content-type')}")
            wav_data = r.read()
            
            # Guardar audio en español
            filename = "audio_espanol.wav"
            with open(filename, "wb") as f:
                f.write(wav_data)
            print(f"🔊 Audio guardado: {filename} ({len(wav_data):,} bytes)")
            print(f"▶️  Para reproducir: open {filename}")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_spanish_streaming():
    """Prueba streaming en español"""
    payload = {
        "text": "Primera frase en español. Segunda frase para probar el streaming. Tercera frase final.",
        "lang": "e",        # ESPAÑOL
        "voice": "af_heart",
        "speed": 1.0
    }
    
    print(f"\n🌊 Probando STREAMING en español...")
    
    req = urllib.request.Request(
        f"{BASE}/tts/stream",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "multipart/mixed",
        },
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"✅ Streaming: {r.status} {r.headers.get('content-type')}")
            stream_data = r.read()
            
            # Guardar stream completo
            with open("stream_espanol.bin", "wb") as f:
                f.write(stream_data)
            print(f"📦 Stream guardado: stream_espanol.bin ({len(stream_data):,} bytes)")
            return True
            
    except Exception as e:
        print(f"❌ Error streaming: {e}")
        return False

if __name__ == "__main__":
    print("🇪🇸 PRUEBA DE TTS EN ESPAÑOL")
    print("=" * 40)
    
    # Verificar que el servidor responde
    try:
        with urllib.request.urlopen(f"{BASE}/") as r:
            info = json.load(r)
            print(f"✅ Servidor activo: {info}")
    except:
        print("❌ Servidor no disponible en http://127.0.0.1:8010")
        exit(1)
    
    # Pruebas en español
    success1 = test_spanish_tts()
    success2 = test_spanish_streaming()
    
    if success1 and success2:
        print("\n🎉 ¡TODO FUNCIONANDO EN ESPAÑOL!")
        print("🔊 Archivos generados:")
        print("   - audio_espanol.wav (audio completo)")
        print("   - stream_espanol.bin (datos de streaming)")
    else:
        print("\n❌ Hubo errores en las pruebas")
