"""ObraCtrl — backend (FastAPI).

Arquitectura Clean + Screaming (§12.11): la dependencia apunta hacia adentro.
    domain/          núcleo puro — no conoce FastAPI, SQLModel ni RLS
    application/     casos de uso — orquestan el dominio vía puertos
    adapters/        borde — API, repos, Excel, exportadores
    infrastructure/  PostgreSQL+RLS, Alembic, jobs, R2, push/email
"""

__version__ = "0.1.0"
