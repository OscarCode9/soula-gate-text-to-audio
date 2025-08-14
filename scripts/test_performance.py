#!/usr/bin/env python3
"""
Script para probar las mejoras de performance en la API de TTS.
Prueba textos largos, streaming mejorado y chunks pequeños.
"""
import json
import time
import urllib.request
import urllib.error
import os

BASE = "http://13.58.240.149:5032"

def wait_for_server():
    """Espera hasta que el servidor responda"""
    for i in range(30):  # 30 intentos
        try:
            with urllib.request.urlopen(f"{BASE}/") as r:
                if r.status == 200:
                    print("✓ Servidor respondiendo")
                    return True
        except urllib.error.URLError:
            pass
        print(f"Esperando servidor... {i+1}/30")
        time.sleep(1)
    return False

def test_short_text():
    """Prueba con texto corto"""
    print("\n🔊 Probando texto corto...")
    payload = {
        "text": "Hello world, this is a short test.",
        "lang": "a", 
        "voice": "af_heart",
        "speed": 1.0,
        "max_chunk_words": 20
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/tts", 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=60) as r:
            wav_data = r.read()
            elapsed = time.time() - start_time
            
            filename = "test_short.wav"
            with open(filename, "wb") as f:
                f.write(wav_data)
                
            print(f"✓ Texto corto: {elapsed:.2f}s, {len(wav_data)} bytes -> {filename}")
            return True
    except Exception as e:
        print(f"✗ Error texto corto: {e}")
        return False

def test_long_text():
    """Prueba con texto largo para ver las mejoras de performance"""
    print("\n📖 Probando texto largo...")
    long_text = """
    This is a much longer text to test the performance improvements. 
    The new system should split this into smaller chunks and process them more efficiently.
    We expect to see better performance with parallel processing for longer texts like this one.
    Each chunk should be processed independently, allowing for better resource utilization.
    The streaming should also be much more responsive with smaller chunks being sent continuously.
    This will make the user experience much better when dealing with longer content.
    The smart text splitting should respect sentence boundaries while keeping chunks at a reasonable size.
    """
    
    payload = {
        "text": long_text.strip(),
        "lang": "a", 
        "voice": "af_heart",
        "speed": 1.0,
        "max_chunk_words": 25
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/tts", 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            wav_data = r.read()
            elapsed = time.time() - start_time
            
            filename = "test_long.wav"
            with open(filename, "wb") as f:
                f.write(wav_data)
                
            chars_per_second = len(long_text) / elapsed
            print(f"✓ Texto largo: {elapsed:.2f}s, {len(wav_data)} bytes, {chars_per_second:.1f} chars/s -> {filename}")
            return True
    except Exception as e:
        print(f"✗ Error texto largo: {e}")
        return False

def test_streaming():
    """Prueba el streaming mejorado"""
    print("\n🌊 Probando streaming mejorado...")
    
    text = """
    This is a streaming test with multiple sentences. Each sentence should be processed as a separate chunk.
    The new streaming system should send smaller, more frequent chunks for a better user experience.
    You should see multiple audio chunks being received in real-time instead of waiting for the entire text.
    This makes the application feel much more responsive and natural for longer content.
    """
    
    payload = {
        "text": text.strip(),
        "lang": "a", 
        "voice": "af_heart",
        "speed": 1.0,
        "max_chunk_words": 15  # Chunks más pequeños para streaming
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/tts/stream", 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        start_time = time.time()
        chunks_received = 0
        total_bytes = 0
        
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"Content-Type: {r.headers.get('content-type')}")
            
            # Simular recepción de chunks
            chunk_times = []
            while True:
                chunk = r.read(8192)  # Lee en chunks de 8KB
                if not chunk:
                    break
                    
                chunk_time = time.time() - start_time
                chunks_received += 1
                total_bytes += len(chunk)
                chunk_times.append(chunk_time)
                
                if chunks_received <= 10:  # Solo mostrar primeros 10 chunks
                    print(f"  Chunk {chunks_received}: {len(chunk)} bytes @ {chunk_time:.2f}s")
        
        elapsed = time.time() - start_time
        print(f"✓ Streaming: {elapsed:.2f}s total, {chunks_received} chunks, {total_bytes} bytes")
        
        if chunk_times:
            avg_interval = (chunk_times[-1] - chunk_times[0]) / max(1, len(chunk_times) - 1)
            print(f"  Intervalo promedio entre chunks: {avg_interval:.3f}s")
        
        return True
    except Exception as e:
        print(f"✗ Error streaming: {e}")
        return False

def test_spanish():
    """Prueba con texto en español"""
    print("\n🇪🇸 Probando texto en español...")
    
    spanish_text = """
    Hola, este es un texto de prueba en español. 
    El sistema debería poder manejar diferentes idiomas correctamente.
    Los chunks deberían dividirse respetando las oraciones en español.
    """
    
    payload = {
        "text": spanish_text.strip(),
        "lang": "e",  # Español
        "voice": "ef_heart", 
        "speed": 1.0,
        "max_chunk_words": 20
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/tts", 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=60) as r:
            wav_data = r.read()
            elapsed = time.time() - start_time
            
            filename = "test_spanish.wav"
            with open(filename, "wb") as f:
                f.write(wav_data)
                
            print(f"✓ Español: {elapsed:.2f}s, {len(wav_data)} bytes -> {filename}")
            return True
    except Exception as e:
        print(f"✗ Error español: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Probando mejoras de performance en Kokoro TTS...")
    
    if not wait_for_server():
        print("✗ Servidor no disponible")
        exit(1)
    
    tests = [
        ("Texto corto", test_short_text),
        ("Texto largo", test_long_text),
        ("Streaming", test_streaming),
        ("Español", test_spanish),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Error en {test_name}: {e}")
            failed += 1
    
    print(f"\n📊 Resultados: {passed} ✓, {failed} ✗")
    
    if failed > 0:
        print("❌ Algunas pruebas fallaron")
        exit(1)
    else:
        print("✅ ¡Todas las pruebas pasaron!")
