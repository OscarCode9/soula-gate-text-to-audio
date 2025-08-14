# Proyecto Kokoro TTS - Servicio de Streaming

✅ **COMPLETADO** - Servicio de texto a voz usando Kokoro TTS con FastAPI

## ¿Qué se implementó?

### ✅ Requisitos cumplidos:
- [x] **Servicio de streaming** - Endpoint `/tts/stream` con multipart/mixed
- [x] **API HTTP** - FastAPI con endpoints REST
- [x] **CPU/GPU automático** - Usa CPU por defecto, GPU si está disponible
- [x] **Kokoro TTS** - Integrado con modelo 82M de calidad
- [x] **Simple y funcional** - Mínimo viable, fácil de usar

### 🏗️ Estructura del proyecto:
```
soulgate-text-to-audio/
├── app/
│   ├── __init__.py
│   └── main.py          # FastAPI app principal
├── scripts/
│   ├── test_api.py      # Test completo (streaming + no-streaming)
│   └── test_simple.py   # Test básico con espera
├── requirements.txt     # Dependencias
└── README.md           # Documentación
```

### 🎯 Endpoints disponibles:

1. **GET /** - Info del servicio
2. **POST /tts** - Texto → WAV completo (no streaming)
3. **POST /tts/stream** - Texto → Stream multipart de chunks WAV

### 🚀 Cómo usar:

1. **Instalar dependencias:**
```bash
pip install -r requirements.txt
```

2. **Ejecutar servidor:**
```bash
# Con aceleración Apple Silicon (opcional)
export PYTORCH_ENABLE_MPS_FALLBACK=1

# Iniciar servidor
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

3. **Probar API:**
```bash
# Test básico
python scripts/test_simple.py

# Test completo
TTS_BASE=http://127.0.0.1:8010 python scripts/test_api.py
```

### 🎛️ Parámetros soportados:
- `text` (str): Texto a sintetizar
- `lang` (str): Idioma ('a'=inglés US, 'e'=español, 'f'=francés, etc.)
- `voice` (str): Voz (ej: 'af_heart', 'af_sarah')
- `speed` (float): Velocidad 0.5-2.0

### 📝 Ejemplos de uso:

**Curl - WAV completo:**
```bash
curl -X POST 'http://127.0.0.1:8010/tts' \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hola mundo", "lang": "e", "voice": "af_heart"}' \
  --output audio.wav
```

**Curl - Streaming:**
```bash
curl -N -X POST 'http://127.0.0.1:8010/tts/stream' \
  -H 'Content-Type: application/json' \
  -d '{"text": "Primera oración. Segunda oración.", "lang": "e"}' \
  -H 'Accept: multipart/mixed'
```

### ⚡ Características técnicas:
- **CPU/GPU**: Auto-detecta hardware disponible
- **Formatos**: WAV 24kHz, 16-bit
- **Streaming**: Multipart/mixed, un chunk por oración
- **Modelos**: Kokoro-82M (descarga automática ~327MB)
- **Idiomas**: Inglés, español, francés, italiano, portugués, hindi, japonés, chino

### 🎊 Estado: ¡LISTO PARA USAR!

El servidor está descargando el modelo Kokoro en primer uso. Una vez completado (~2-3 minutos), estará operativo para síntesis de voz en tiempo real.
