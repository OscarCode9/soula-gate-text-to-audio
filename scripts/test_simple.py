#!/usr/bin/env python3
"""
Script simple para probar la API cuando el modelo esté listo.
Espera hasta que el servidor responda correctamente.
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8010"

def wait_for_server():
    """Espera hasta que el servidor responda"""
    for i in range(60):  # 60 intentos
        try:
            with urllib.request.urlopen(f"{BASE}/") as r:
                if r.status == 200:
                    print("✓ Servidor respondiendo")
                    return True
        except urllib.error.URLError:
            pass
        print(f"Esperando servidor... {i+1}/60")
        time.sleep(2)
    return False

def test_simple_tts():
    """Prueba simple de TTS con texto corto"""
    payload = {
        "text": "Hello world",
        "lang": "a", 
        "voice": "af_heart",
        "speed": 1.0
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/tts", 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print(f"✓ TTS Response: {r.status} {r.headers.get('content-type')}")
            wav_data = r.read()
            with open("test_output.wav", "wb") as f:
                f.write(wav_data)
            print(f"✓ Guardado test_output.wav ({len(wav_data)} bytes)")
            return True
    except Exception as e:
        print(f"✗ Error TTS: {e}")
        return False

if __name__ == "__main__":
    print("🔊 Probando API de Kokoro TTS...")
    
    if not wait_for_server():
        print("✗ Servidor no disponible")
        exit(1)
    
    if test_simple_tts():
        print("✓ ¡API funcionando correctamente!")
    else:
        print("✗ Error en la API")
        exit(1)
