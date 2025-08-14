#!/usr/bin/env python3
"""
Script para probar diferentes configuraciones de chunks y encontrar la configuración óptima.
"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8010"

def test_chunk_config(chunk_size, text, test_name):
    """Prueba una configuración específica de chunks"""
    payload = {
        "text": text,
        "lang": "a", 
        "voice": "af_heart",
        "speed": 1.0,
        "max_chunk_words": chunk_size
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
            
            chars_per_second = len(text) / elapsed
            words = len(text.split())
            
            return {
                'success': True,
                'time': elapsed,
                'chars_per_second': chars_per_second,
                'audio_size': len(wav_data),
                'text_words': words,
                'chunk_size': chunk_size
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'chunk_size': chunk_size
        }

def test_streaming_config(chunk_size, text, test_name):
    """Prueba una configuración específica para streaming"""
    payload = {
        "text": text,
        "lang": "a", 
        "voice": "af_heart",
        "speed": 1.0,
        "max_chunk_words": chunk_size
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
        first_chunk_time = None
        
        with urllib.request.urlopen(req, timeout=60) as r:
            while True:
                chunk = r.read(4096)
                if not chunk:
                    break
                    
                if first_chunk_time is None:
                    first_chunk_time = time.time() - start_time
                    
                chunks_received += 1
                total_bytes += len(chunk)
        
        total_time = time.time() - start_time
        
        return {
            'success': True,
            'total_time': total_time,
            'first_chunk_time': first_chunk_time,
            'chunks_received': chunks_received,
            'total_bytes': total_bytes,
            'chunk_size': chunk_size
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'chunk_size': chunk_size
        }

def main():
    print("🔬 Probando diferentes configuraciones de chunks...\n")
    
    # Textos de prueba de diferentes longitudes
    texts = {
        "corto": "Hello world, this is a short test message.",
        "medio": """
        This is a medium length text to test the chunk processing.
        It contains multiple sentences and should be split into several chunks.
        The performance should be good for this kind of content length.
        """.strip(),
        "largo": """
        This is a much longer text that will really test the performance improvements.
        The system needs to handle this efficiently by breaking it into appropriate chunks.
        Each chunk should be processed independently for better resource utilization.
        The streaming should be responsive and provide chunks as soon as they are ready.
        We want to find the optimal chunk size that balances processing speed with responsiveness.
        Too small chunks might create overhead, while too large chunks might feel slow.
        The goal is to find the sweet spot that provides the best user experience.
        This text should help us determine what works best in practice.
        """.strip()
    }
    
    # Diferentes tamaños de chunk para probar
    chunk_sizes = [10, 15, 20, 25, 30, 40, 50]
    
    print("=== PRUEBAS DE PROCESAMIENTO DIRECTO ===\n")
    
    for text_name, text in texts.items():
        print(f"📝 Texto {text_name} ({len(text)} chars, {len(text.split())} palabras):")
        
        results = []
        for chunk_size in chunk_sizes:
            print(f"  Probando chunks de {chunk_size} palabras...", end=" ")
            result = test_chunk_config(chunk_size, text, text_name)
            
            if result['success']:
                print(f"✓ {result['time']:.2f}s ({result['chars_per_second']:.1f} chars/s)")
                results.append(result)
            else:
                print(f"✗ {result['error']}")
        
        if results:
            # Encontrar el mejor resultado
            best = min(results, key=lambda x: x['time'])
            print(f"  🏆 Mejor: {best['chunk_size']} palabras ({best['time']:.2f}s)\n")
        else:
            print("  ❌ Todas las pruebas fallaron\n")
    
    print("\n=== PRUEBAS DE STREAMING ===\n")
    
    # Solo probar streaming con texto medio y largo
    for text_name in ["medio", "largo"]:
        text = texts[text_name]
        print(f"🌊 Streaming {text_name} ({len(text)} chars):")
        
        results = []
        for chunk_size in chunk_sizes:
            print(f"  Probando chunks de {chunk_size} palabras...", end=" ")
            result = test_streaming_config(chunk_size, text, text_name)
            
            if result['success']:
                print(f"✓ Primer chunk: {result['first_chunk_time']:.2f}s, Total: {result['total_time']:.2f}s")
                results.append(result)
            else:
                print(f"✗ {result['error']}")
        
        if results:
            # Mejor para streaming = menor tiempo al primer chunk
            best_streaming = min(results, key=lambda x: x['first_chunk_time'])
            best_total = min(results, key=lambda x: x['total_time'])
            
            print(f"  🚀 Más rápido primer chunk: {best_streaming['chunk_size']} palabras ({best_streaming['first_chunk_time']:.2f}s)")
            print(f"  ⚡ Más rápido total: {best_total['chunk_size']} palabras ({best_total['total_time']:.2f}s)\n")
        else:
            print("  ❌ Todas las pruebas de streaming fallaron\n")

if __name__ == "__main__":
    main()
