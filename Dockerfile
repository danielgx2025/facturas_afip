# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13-slim

# ---------- Stage 1: builder ----------
FROM python:${PYTHON_VERSION} AS builder

# git: necesario SOLO para instalar pyafipws (versión Python 3, desde GitHub)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Deps primero (capa cacheable). setuptools<74 (en requirements) restituye distutils.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# pyafipws: Python 3, SIN dependencias. RECOMENDADO fijar un commit para builds
# reproducibles, p.ej. ...pyafipws.git@<commit-sha>
RUN pip install --no-cache-dir --no-deps \
    git+https://github.com/reingart/pyafipws.git

# ---------- Stage 2: runtime ----------
FROM python:${PYTHON_VERSION} AS runtime
ARG APP_UID=1000

# tzdata para fecha local Argentina (AFIP). git ya NO se necesita en runtime.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Argentina/Buenos_Aires

RUN useradd --create-home --uid ${APP_UID} app
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# Normaliza CRLF→LF (por si se editó en Windows), da permisos y prepara carpetas
RUN sed -i 's/\r$//' docker-entrypoint.sh \
    && chmod +x docker-entrypoint.sh \
    && mkdir -p certs pdfs logs .afip_cache \
    && chown -R app:app /app

USER app
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
