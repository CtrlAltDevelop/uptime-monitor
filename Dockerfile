FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# ping(8) is used by the "ping" check type
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so this layer is cached until pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000

CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
