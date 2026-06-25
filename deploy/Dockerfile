FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
# If uv.lock exists, copy it too
COPY uv.lock* .

# Install dependencies
# We use --no-install-project because we haven't copied the source yet
RUN uv sync --frozen --no-dev || uv pip install .

# Copy the application code
COPY never_again/ ./never_again/

# Set PYTHONPATH to include the current directory so imports work
ENV PYTHONPATH=/app

EXPOSE 8742

# Update command to use the correct module path
CMD ["uvicorn", "never_again.server.app:app", "--host", "0.0.0.0", "--port", "8742"]
