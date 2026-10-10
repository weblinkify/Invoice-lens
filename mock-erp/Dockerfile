# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY mock_erp ./mock_erp
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 9000
HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health')"
CMD ["uvicorn", "mock_erp.main:app", "--host", "0.0.0.0", "--port", "9000"]
