FROM python:3.14-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    UV_PYTHON=/usr/local/bin/python3

CMD ["uv", "run", "python", "serve_output.py"]
