# ObraCtrl API — imagen de producción (Render, §12.8)
FROM python:3.11-slim AS base

# WeasyPrint necesita estas librerías nativas para generar PDF (§12.2)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
      libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Capa de dependencias aparte: el código cambia mucho más seguido
COPY pyproject.toml constraints.txt ./
COPY src ./src
# `-c constraints.txt` fija lo que se probó. Sin esto, un redespliegue podía
# traer una versión de FastAPI que nunca pasó por CI (§12.8).
RUN pip install --no-cache-dir . -c constraints.txt

# No corre como root
RUN useradd --create-home --uid 10001 obractrl
USER obractrl

EXPOSE 8000

# Render inyecta $PORT
CMD ["sh", "-c", "uvicorn obractrl.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
