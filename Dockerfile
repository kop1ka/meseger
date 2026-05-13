# Messenger Docker Image - Optimized
FROM python:3.12-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev libffi-dev

WORKDIR /app

# Copy and install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.12-alpine

# Install runtime dependencies only
RUN apk add --no-cache libffi

# Create non-root user for security
RUN addgroup -g 1000 appgroup && \
    adduser -u 1000 -G appgroup -D appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application files
COPY server.py .
COPY index.html .
COPY migrations/ ./migrations/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:$PATH" \
    PORT=8765 \
    MESSENGER_DB_PATH=/app/data/messenger.db

# Create data directory for persistent storage
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE ${PORT}

# Health check with configurable port
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:${PORT}/ || exit 1

# Graceful shutdown with signal handling
ENTRYPOINT ["python", "-u"]
CMD ["server.py"]
