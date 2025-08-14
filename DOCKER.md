# Docker Setup para Soulgate TTS

Este directorio contiene la configuración Docker para ejecutar el servicio Soulgate TTS usando Kokoro en el puerto 5032.

## Archivos Docker

- `Dockerfile` - Imagen Docker para el servicio TTS
- `docker-compose.yml` - Configuración de servicios
- `.dockerignore` - Archivos a ignorar en el build
- `docker-helper.sh` - Script helper para facilitar el manejo

## Inicio Rápido

### 1. Construir e Iniciar el Servicio

```bash
# Usando docker-compose directamente
docker-compose up -d

# O usando el script helper
./docker-helper.sh start
```

### 2. Verificar que el Servicio está Funcionando

```bash
# Verificar estado
./docker-helper.sh status

# Ver logs
./docker-helper.sh logs

# Probar la API
curl http://localhost:5032/
```

### 3. Probar el TTS

```bash
# Endpoint simple
curl -X POST "http://localhost:5032/tts" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hola mundo","lang":"e","voice":"af_heart"}' \
  --output test.wav

# O usar el test integrado
./docker-helper.sh test
```

## Comandos del Script Helper

```bash
./docker-helper.sh build       # Construir imagen
./docker-helper.sh start       # Iniciar servicio
./docker-helper.sh stop        # Detener servicio
./docker-helper.sh restart     # Reiniciar servicio
./docker-helper.sh logs        # Ver logs
./docker-helper.sh status      # Ver estado
./docker-helper.sh shell       # Abrir shell en contenedor
./docker-helper.sh clean       # Limpiar todo
./docker-helper.sh test        # Probar API
./docker-helper.sh help        # Ayuda
```

## Configuración del Servicio

### Puerto
- **Puerto interno**: 5032
- **Puerto externo**: 5032 (configurable en docker-compose.yml)

### Endpoints Disponibles
- `GET /` - Información del servicio
- `POST /tts` - Síntesis de texto a audio (respuesta completa)
- `POST /tts/stream` - Síntesis streaming (multipart)

### Parámetros TTS
```json
{
  "text": "Texto a sintetizar",
  "lang": "e",           // Código de idioma: a,b,e,f,h,i,j,p,z
  "voice": "af_heart",   // Nombre de la voz
  "speed": 1.0           // Velocidad (0.5-2.0)
}
```

## Volúmenes

- `kokoro-cache`: Cache persistente para los modelos de Kokoro
  - Ubicación interna: `/home/appuser/.cache/kokoro`

## Troubleshooting

### El servicio no inicia
```bash
# Ver logs detallados
docker-compose logs soulgate-tts

# Verificar el build
docker-compose build --no-cache
```

### Problemas de memoria
El servicio necesita al menos 2GB de RAM para los modelos de Kokoro.

### Actualizar el código
```bash
# Detener, reconstruir e iniciar
./docker-helper.sh stop
./docker-helper.sh build
./docker-helper.sh start
```

### Limpieza completa
```bash
# Eliminar todo (contenedores, imágenes, volúmenes)
./docker-helper.sh clean
```

## Configuración de Producción

Para producción, puedes descomentar la sección nginx en `docker-compose.yml` y crear un archivo `nginx.conf` para reverse proxy y load balancing.

### Variables de Entorno

- `PYTHONPATH=/app`
- `PYTHONUNBUFFERED=1`

### Health Checks

El contenedor incluye health checks automáticos que verifican el endpoint `/` cada 30 segundos.

## Desarrollo

Para desarrollo activo, puedes montar el código como volumen:

```yaml
volumes:
  - ./app:/app/app:ro
  - ./scripts:/app/scripts:ro
```

Agrega esto al servicio `soulgate-tts` en docker-compose.yml para hot-reload durante desarrollo.
