# Deployment en AWS para Soulgate TTS

Esta guía explica cómo solucionar problemas comunes al deployar el servicio Soulgate TTS en AWS.

## Problema de Permisos Resuelto

### Error Original
```
PermissionError: [Errno 13] Permission denied: '/home/appuser/.cache/huggingface'
```

### Solución Implementada

1. **Dockerfile actualizado** con:
   - Creación explícita de directorios cache con permisos correctos
   - Variables de entorno para HuggingFace
   - Instalación de `wget` para healthchecks

2. **Docker-compose.yml actualizado** con:
   - Volúmenes persistentes para cache de HuggingFace y Kokoro
   - Variables de entorno para controlar ubicación de cache
   - Healthcheck actualizado usando `wget`

## Configuración de Deployment

### Variables de Entorno Importantes

```bash
# Cache de HuggingFace
HF_HOME=/home/appuser/.cache/huggingface
TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface
HF_HUB_CACHE=/home/appuser/.cache/huggingface

# Aplicación
PYTHONPATH=/app
PYTHONUNBUFFERED=1
```

### Volúmenes Persistentes

```yaml
volumes:
  kokoro-cache:
    driver: local
  huggingface-cache:
    driver: local
```

## Deployment en AWS EC2

### 1. Preparación de la Instancia

```bash
# Instalar Docker y docker-compose
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Instalar docker-compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Deployment del Servicio

```bash
# Clonar el repositorio
git clone <tu-repositorio>
cd soulgate-text-to-audio

# Hacer ejecutable el script helper
chmod +x docker-helper.sh

# Iniciar el servicio
./docker-helper.sh start

# Verificar estado
./docker-helper.sh status
./docker-helper.sh logs
```

### 3. Configuración de Firewall/Security Groups

Asegúrate de que el puerto 5032 esté abierto en los Security Groups de AWS:

```
Type: Custom TCP
Port: 5032
Source: 0.0.0.0/0 (o tu rango de IPs específico)
```

## Deployment en AWS ECS

### 1. Task Definition

```json
{
  "family": "soulgate-tts",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "soulgate-tts",
      "image": "tu-repositorio/soulgate-tts:latest",
      "portMappings": [
        {
          "containerPort": 5032,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "PYTHONPATH", "value": "/app"},
        {"name": "PYTHONUNBUFFERED", "value": "1"},
        {"name": "HF_HOME", "value": "/home/appuser/.cache/huggingface"},
        {"name": "TRANSFORMERS_CACHE", "value": "/home/appuser/.cache/huggingface"},
        {"name": "HF_HUB_CACHE", "value": "/home/appuser/.cache/huggingface"}
      ],
      "mountPoints": [
        {
          "sourceVolume": "huggingface-cache",
          "containerPath": "/home/appuser/.cache/huggingface"
        },
        {
          "sourceVolume": "kokoro-cache",
          "containerPath": "/home/appuser/.cache/kokoro"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/soulgate-tts",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "huggingface-cache",
      "dockerVolumeConfiguration": {
        "scope": "shared",
        "autoprovision": true,
        "driver": "local"
      }
    },
    {
      "name": "kokoro-cache",
      "dockerVolumeConfiguration": {
        "scope": "shared",
        "autoprovision": true,
        "driver": "local"
      }
    }
  ]
}
```

### 2. Service Configuration

```json
{
  "serviceName": "soulgate-tts-service",
  "cluster": "tu-cluster",
  "taskDefinition": "soulgate-tts:1",
  "desiredCount": 1,
  "launchType": "FARGATE",
  "networkConfiguration": {
    "awsvpcConfiguration": {
      "subnets": ["subnet-12345", "subnet-67890"],
      "securityGroups": ["sg-12345"],
      "assignPublicIp": "ENABLED"
    }
  },
  "loadBalancers": [
    {
      "targetGroupArn": "arn:aws:elasticloadbalancing:region:account:targetgroup/soulgate-tts",
      "containerName": "soulgate-tts",
      "containerPort": 5032
    }
  ]
}
```

## Monitoring y Troubleshooting

### Comandos Útiles

```bash
# Ver logs en tiempo real
./docker-helper.sh logs

# Verificar estado del contenedor
docker ps

# Verificar volúmenes
docker volume ls

# Limpiar cache si hay problemas
./docker-helper.sh clean-cache

# Restart completo
./docker-helper.sh restart
```

### Problemas Comunes

1. **Out of Memory**: Aumentar memoria de la instancia EC2/ECS
2. **Slow Model Loading**: El primer request puede tardar ~30 segundos
3. **Permission Issues**: Usar `./docker-helper.sh clean-cache` y reiniciar

### Verificación de Health

```bash
# Check manual
curl http://localhost:5032/

# Test completo de API
./docker-helper.sh test
```

## Optimizaciones para Producción

1. **Pre-download de modelos**: Ejecutar un request inicial para pre-cargar modelos
2. **Load Balancer**: Usar ALB en AWS para distribuir carga
3. **Auto Scaling**: Configurar ECS Auto Scaling basado en CPU/memoria
4. **Monitoring**: CloudWatch para métricas y logs
5. **Cache persistente**: Usar EFS para compartir cache entre instancias

## Backup y Recovery

```bash
# Backup de volúmenes
docker run --rm -v soulgate-text-to-audio_huggingface-cache:/data -v $(pwd):/backup alpine tar czf /backup/hf-cache-backup.tar.gz -C /data .
docker run --rm -v soulgate-text-to-audio_kokoro-cache:/data -v $(pwd):/backup alpine tar czf /backup/kokoro-cache-backup.tar.gz -C /data .

# Restore de volúmenes
docker run --rm -v soulgate-text-to-audio_huggingface-cache:/data -v $(pwd):/backup alpine tar xzf /backup/hf-cache-backup.tar.gz -C /data
docker run --rm -v soulgate-text-to-audio_kokoro-cache:/data -v $(pwd):/backup alpine tar xzf /backup/kokoro-cache-backup.tar.gz -C /data
```
