#!/bin/bash

# Soulgate TTS Docker Helper Script
# Usage: ./docker-helper.sh [command]

set -e

PROJECT_NAME="soulgate-tts"
CONTAINER_NAME="soulgate-kokoro-tts"
PORT="5032"

show_help() {
    echo "Soulgate TTS Docker Helper"
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  build       Build the Docker image"
    echo "  start       Start the service (build if needed)"
    echo "  stop        Stop the service"
    echo "  restart     Restart the service"
    echo "  logs        Show service logs"
    echo "  status      Show service status"
    echo "  shell       Open shell in running container"
    echo "  clean       Remove containers and images"
    echo "  test        Test the API endpoints"
    echo "  help        Show this help message"
    echo ""
    echo "Service will be available at: http://localhost:$PORT"
}

build_image() {
    echo "Building Docker image..."
    docker-compose build
}

start_service() {
    echo "Starting Soulgate TTS service on port $PORT..."
    docker-compose up -d
    echo "Service started! Available at: http://localhost:$PORT"
    echo "Use '$0 logs' to see the logs"
}

stop_service() {
    echo "Stopping Soulgate TTS service..."
    docker-compose down
}

restart_service() {
    echo "Restarting Soulgate TTS service..."
    docker-compose restart
}

show_logs() {
    echo "Showing service logs (Ctrl+C to exit)..."
    docker-compose logs -f
}

show_status() {
    echo "Service status:"
    docker-compose ps
    echo ""
    echo "Health check:"
    if curl -s "http://localhost:$PORT/" > /dev/null 2>&1; then
        echo "✅ Service is healthy and responding"
    else
        echo "❌ Service is not responding"
    fi
}

open_shell() {
    echo "Opening shell in running container..."
    docker-compose exec soulgate-tts /bin/bash
}

clean_all() {
    echo "Cleaning up containers and images..."
    docker-compose down --rmi all --volumes --remove-orphans
    echo "Cleanup complete"
}

test_api() {
    echo "Testing API endpoints..."
    echo ""
    
    # Test root endpoint
    echo "1. Testing root endpoint..."
    curl -s "http://localhost:$PORT/" | jq . || echo "Failed to reach root endpoint"
    echo ""
    
    # Test TTS endpoint
    echo "2. Testing TTS endpoint..."
    curl -s -X POST "http://localhost:$PORT/tts" \
        -H "Content-Type: application/json" \
        -d '{"text":"Hola mundo, esto es una prueba","lang":"e","voice":"af_heart"}' \
        --output test_response.wav
    
    if [ -f "test_response.wav" ]; then
        echo "✅ TTS endpoint working - audio saved as test_response.wav"
    else
        echo "❌ TTS endpoint failed"
    fi
    echo ""
    
    echo "API test complete!"
}

# Main script logic
case "${1:-help}" in
    build)
        build_image
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    shell)
        open_shell
        ;;
    clean)
        clean_all
        ;;
    test)
        test_api
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
