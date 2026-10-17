# syntax=docker/dockerfile:1

# Two stages. The builder resolves the committed lock into a self-contained
# virtualenv; the runtime stage copies that venv plus the two source files onto a
# clean base, so the uv binary, package caches and any tooling a wheel needed stay
# out of the final image.
#
# Measured on amd64 with `docker image ls` (same app, same lock, two bases):
#   python:3.13-alpine          91 MB   <- used here
#   python:3.13-slim-bookworm  168 MB
# Both were smoke-tested end to end, including real upstream HTTPS calls, so
# musl's resolver and CA bundle are exercised rather than assumed. Distroless was
# rejected on evidence: gcr.io/distroless/python3-debian12 ships Python 3.11, so
# it would silently drop this project off 3.13 for ~1 MB of base image.
#
# If a future dependency publishes no musllinux wheel, swap both FROM lines to
# python:3.13-slim-bookworm, replace the apk lines with nothing, and use
# groupadd/useradd instead of addgroup/adduser.

FROM python:3.13-alpine AS builder

# Same uv version that wrote uv.lock (0.12.19), so --locked is validated by the
# resolver that produced the lock. Only the static binaries come across, not that
# image's base.
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

# COMPILE_BYTECODE: .pyc files are written here, at build time, because the
#   runtime user has no write access to /opt/venv.
# LINK_MODE=copy: builder and runtime are separate filesystems, so hardlinks into
#   uv's cache cannot survive the COPY.
# PYTHON_DOWNLOADS=0: never fetch an interpreter; the base image's 3.13 is used.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# libstdc++ is what the musllinux wheels behind uvicorn[standard] (uvloop,
# httptools) link against at runtime.
RUN apk add --no-cache libstdc++

# pyproject.toml declares no [build-system], so this project is never built or
# installed: uv only needs the metadata and the lock. --locked fails instead of
# re-resolving a stale lock; --no-dev leaves out httpx2/httpx from the dev group.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

FROM python:3.13-alpine AS runtime

# Fixed numeric uid/gid so mounted volumes keep predictable ownership; no home
# directory and no login shell.
RUN apk add --no-cache libstdc++ \
    && addgroup -g 10001 app \
    && adduser -D -u 10001 -G app -h /app -s /sbin/nologin app

WORKDIR /app

# Must be the same absolute path as in the builder stage: the venv's pyvenv.cfg
# and its console scripts record it.
COPY --from=builder /opt/venv /opt/venv

# Runtime source only. app.py imports aion2_api.py; neither reads files at import.
COPY app.py aion2_api.py ./

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001

EXPOSE 8000

# No curl or wget in the image, so probe with the venv interpreter and urllib from
# the standard library. urlopen raises on any non-2xx, so this exits 0 only when
# "/" answers 200; "/" is the static index route and touches no upstream service.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"

# Binds all interfaces so the published port works; no --reload outside dev.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
