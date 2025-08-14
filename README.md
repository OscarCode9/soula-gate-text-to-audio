# Soulgate Text-to-Audio (Kokoro TTS)

Servicio simple en Python para convertir texto a voz usando Kokoro TTS, con API HTTP y streaming.

- CPU por defecto. Si hay GPU (CUDA/MPS), PyTorch puede aprovecharla automáticamente.
- Endpoints:
  - POST /tts -> devuelve WAV completo
  - POST /tts/stream -> streaming multipart de fragmentos WAV

## Requisitos

- Python 3.9+
- macOS recomendado (funciona también en Linux/Windows)

## Instalación

1) Crear y activar un entorno virtual (opcional):

```bash
python -m venv .venv
source .venv/bin/activate
```

2) Instalar dependencias:

```bash
pip install -r requirements.txt
```

Nota: se descargarán los pesos del modelo la primera vez que se ejecute el endpoint de TTS.

En Apple Silicon puedes habilitar MPS fallback:

```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

## Ejecutar el servidor

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Usar la API

- Texto a WAV (no streaming):

```bash
curl -X POST 'http://localhost:8000/tts' \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hola, esto es una prueba de texto a voz con Kokoro.", "lang":"e", "voice":"af_heart", "speed":1.0}' \
  --output out.wav
```

- Streaming (multipart/mixed) de fragmentos WAV (una parte por oración):

```bash
curl -N -X POST 'http://localhost:8000/tts/stream' \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hola mundo. Esto es streaming.", "lang":"e", "voice":"af_heart"}' \
  -H 'Accept: multipart/mixed'
```

El endpoint de streaming devuelve un stream multipart con límite `--frame`. Cada parte tiene un pequeño archivo WAV.

## Parámetros

- text (str, requerido): texto a sintetizar
- lang (str, opcional): código de idioma de Kokoro (por ejemplo: 'a' inglés EEUU, 'b' inglés UK, 'e' español, 'f' francés, 'i' italiano, 'p' portugués BR, 'h' hindi, 'j' japonés, 'z' chino). Por defecto: 'a'.
- voice (str, opcional): voz, por ejemplo 'af_heart'. Por defecto: 'af_heart'.
- speed (float, opcional): velocidad (1.0 por defecto)

## Notas

- Para algunos idiomas/frases, Kokoro utiliza librería G2P `misaki`. Está incluida en `requirements.txt`.
- En macOS puedes instalar `espeak-ng` para fallback en casos OOD (opcional): `brew install espeak`.

## Licencias

- Kokoro: Apache 2.0 (pesos/modelo)
- Este proyecto: MIT
