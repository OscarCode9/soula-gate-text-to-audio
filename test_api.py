#!/usr/bin/env python3
"""
Test script para verificar la API de Edge TTS
"""
import requests
import sys

BASE_URL = "http://localhost:5032"

def test_root():
    """Test endpoint raíz"""
    print("=" * 50)
    print("🧪 TEST 1: Endpoint raíz /")
    print("=" * 50)
    try:
        r = requests.get(f"{BASE_URL}/")
        print(f"Status: {r.status_code}")
        print(f"Response: {r.json()}")
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_health():
    """Test endpoint de salud"""
    print("\n" + "=" * 50)
    print("🧪 TEST 2: Health check /health")
    print("=" * 50)
    try:
        r = requests.get(f"{BASE_URL}/health")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Engine: {data.get('engine')}")
        print(f"Memory: {data.get('memory', {}).get('usage_mb')}MB")
        return r.status_code == 200 and data.get('status') == 'healthy'
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_voices():
    """Test endpoint de voces"""
    print("\n" + "=" * 50)
    print("🧪 TEST 3: Listar voces /voices")
    print("=" * 50)
    try:
        r = requests.get(f"{BASE_URL}/voices")
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Total voces: {data.get('total_voices')}")
        print(f"Locales disponibles: {len(data.get('by_locale', {}))}")
        # Mostrar algunas voces en español
        es_voices = data.get('by_locale', {}).get('es-MX', [])
        print(f"Voces es-MX: {[v['name'] for v in es_voices[:3]]}")
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_tts_single():
    """Test endpoint TTS simple"""
    print("\n" + "=" * 50)
    print("🧪 TEST 4: TTS simple /tts")
    print("=" * 50)
    try:
        payload = {
            "text": "Hola, esta es una prueba del servidor Edge TTS.",
            "lang": "e",
            "voice": "af_heart",
            "speed": 1.0
        }
        r = requests.post(f"{BASE_URL}/tts", json=payload)
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"Audio size: {len(r.content)} bytes")
        
        # Guardar audio para verificar
        with open("test_output.mp3", "wb") as f:
            f.write(r.content)
        print("✅ Audio guardado en test_output.mp3")
        
        return r.status_code == 200 and len(r.content) > 1000
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_tts_stream():
    """Test endpoint TTS streaming"""
    print("\n" + "=" * 50)
    print("🧪 TEST 5: TTS streaming /tts/stream")
    print("=" * 50)
    try:
        payload = {
            "text": "Este es un test de streaming. El audio se divide en fragmentos.",
            "lang": "e",
            "voice": "af_heart",
            "speed": 1.0
        }
        r = requests.post(f"{BASE_URL}/tts/stream", json=payload, stream=True)
        print(f"Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        
        # Contar chunks
        chunks = 0
        total_size = 0
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                chunks += 1
                total_size += len(chunk)
        
        print(f"Chunks recibidos: {chunks}")
        print(f"Total bytes: {total_size}")
        
        return r.status_code == 200 and total_size > 1000
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_spanish_voice():
    """Test con voz española nativa"""
    print("\n" + "=" * 50)
    print("🧪 TEST 6: Voz española nativa")
    print("=" * 50)
    try:
        payload = {
            "text": "Hola, soy una voz en español de México. ¿Cómo estás?",
            "lang": "e",
            "voice": "es_female",  # Mapea a es-MX-DaliaNeural
            "speed": 1.0
        }
        r = requests.post(f"{BASE_URL}/tts", json=payload)
        print(f"Status: {r.status_code}")
        print(f"Audio size: {len(r.content)} bytes")
        
        with open("test_spanish.mp3", "wb") as f:
            f.write(r.content)
        print("✅ Audio guardado en test_spanish.mp3")
        
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("\n🚀 SOULGATE EDGE TTS - TEST SUITE")
    print("=" * 50)
    
    results = []
    
    results.append(("Endpoint raíz", test_root()))
    results.append(("Health check", test_health()))
    results.append(("Listar voces", test_voices()))
    results.append(("TTS simple", test_tts_single()))
    results.append(("TTS streaming", test_tts_stream()))
    results.append(("Voz española", test_spanish_voice()))
    
    # Resumen
    print("\n" + "=" * 50)
    print("📊 RESUMEN DE TESTS")
    print("=" * 50)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Resultado: {passed}/{len(results)} tests pasados")
    
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    sys.exit(main())
