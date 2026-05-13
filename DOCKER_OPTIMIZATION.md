# Secure Messenger - Docker Configuration

## Optimizations Applied

### Dockerfile Improvements:
1. **Multi-stage build** - Reduces final image size by separating build and runtime stages
2. **Alpine Linux** - Uses python:3.12-alpine for smaller image footprint (~50MB vs ~150MB)
3. **Non-root user** - Enhanced security by running as unprivileged user (appuser)
4. **Layer caching** - Dependencies installed before copying application code
5. **Environment variables** - Properly configured for production use
6. **Health check** - Uses wget instead of Python for lighter weight checks
7. **Signal handling** - Proper ENTRYPOINT/CMD for graceful shutdown
8. **Python optimizations** - PYTHONDONTWRITEBYTECODE and PYTHONUNBUFFERED enabled

### Docker Compose Improvements:
1. **Named volumes** - Database persistence outside container
2. **Resource limits** - CPU and memory constraints to prevent runaway usage
3. **Logging configuration** - Log rotation to prevent disk space issues
4. **Environment variables** - Configurable ports via .env file
5. **Health checks** - Native Docker health monitoring
6. **Explicit network** - Bridge network configuration

### .dockerignore Added:
- Excludes unnecessary files from build context
- Reduces build time and image size
- Prevents sensitive files from being included

## Usage

### Build and Run:
```bash
# Build the image
docker-compose build

# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Environment Variables:
Create a `.env` file to customize:
```env
PORT=8765
HOST_PORT=8765
```

### Health Check:
```bash
docker inspect --format='{{json .State.Health}}' secure-messenger | jq
```

### Resource Monitoring:
```bash
docker stats secure-messenger
```

## Security Features:
- ✅ Non-root user execution
- ✅ Minimal base image (Alpine)
- ✅ No build tools in production image
- ✅ Database persisted in named volume
- ✅ Log rotation configured
- ✅ Resource limits enforced
