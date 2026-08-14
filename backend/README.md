# `backend/` — API FastAPI (Render)

Monolito modular con fachadas. Spec §11 (dominio y API) · §12.2 (stack) ·
§12.11 (arquitectura interna).

## Arquitectura — Clean + Screaming (§12.11)

La dependencia apunta **hacia adentro**. El `domain/` no conoce FastAPI,
SQLModel, RLS ni React: los frameworks viven en el borde.

```
src/obractrl/
├─ domain/            NÚCLEO puro — sin FastAPI/SQLModel/RLS
│  ├─ shared/         diccionario canónico (§8) · value objects (§11.1)
│  │                  semana (§3.1) · folios (§3.2) · IVA (§3.5)
│  ├─ avance/         reglas de captura (§6)
│  ├─ programacion/   motor CPM (§6)
│  ├─ cierres/        flujo autorizar/validar (§4, §6)
│  └─ proyectos/ obras/ estimacion/ materiales/ incidencias/
│     evaluaciones/ catalogos/ reportes/
├─ application/       CASOS DE USO — orquestan el dominio vía puertos
│  ├─ puertos/        interfaces (se implementan en el borde)
│  └─ casos_uso/
├─ adapters/          BORDE
│  ├─ api/            controladores FastAPI + DTOs → OpenAPI → Orval
│  ├─ repos/          repositorios (SQLModel) + RLS
│  ├─ excel/          cargadores por archivo (§10.6) + 3 modos (§10.2)
│  └─ export/         PDF (WeasyPrint) / Excel (OpenPyXL)
└─ infrastructure/    PostgreSQL+RLS, Alembic, jobs (Arq+Redis), R2, push/email
```

Las carpetas de `domain/` son 1:1 con los dominios del §7: **gritan el
dominio, no la tecnología**.

### Las reglas que no se negocian

1. **Ningún archivo de `domain/` importa de `adapters/`, `infrastructure/` ni
   de las apps.** Los puertos se declaran en dominio/aplicación y se
   implementan en el borde.
2. **Cero lógica de negocio en controladores.** Un router valida el DTO,
   delega en el caso de uso y mapea el resultado.
3. **DTOs en el borde.** Las entidades de dominio no cruzan crudas a la API.
4. **Un módulo nunca toca las tablas ni el repositorio de otro**: fachadas y
   eventos de dominio.

Esto **se verifica en CI**, no se deja a la disciplina: `import-linter` tiene
tres contratos en `pyproject.toml` que fallan el build si alguien importa
hacia afuera.

```bash
lint-imports          # regla de dependencia
ruff check src tests  # estilo
mypy                  # tipos (strict)
```

## Qué ya está implementado

| Pieza | Archivo | §  |
|---|---|---|
| Diccionario canónico (invariantes) | `domain/shared/diccionario.py` | §8.2, §8.7 |
| Value objects `Dinero`/`Cantidad`/`Avance`/`PrecioUnitario` | `domain/shared/valores.py` | §11.1 |
| Normalización de FOLIO | `domain/shared/folio.py` | §3.2 |
| Reglas de captura de avance | `domain/avance/reglas.py` | §6 |
| Motor CPM (holgura, ruta crítica, desfase, bloqueo en cascada) | `domain/programacion/cpm.py` | §6 |
| Flujo de cierre (autorizar ≠ validar) | `domain/cierres/reglas.py` | §4, §6 |
| Puertos de persistencia | `application/puertos/repositorios.py` | §12.11 |
| Caso de uso de referencia | `application/casos_uso/capturar_avance.py` | §11.3 B |
| JWT → contexto RLS | `infrastructure/db/sesion.py`, `adapters/api/dependencias.py` | §12.4 |
| Errores de dominio → problem+json | `main.py` | §11.2 |

**79 pruebas de dominio** cubren §6, §3.2, §11.1 y el motor CPM.

## Lo que falta (siguiente iteración)

- Repositorios SQLModel que implementen los puertos (`adapters/repos/`).
- Cablear `PATCH /actividades/{id}/avance` con `CapturarAvance` — hoy el
  endpoint levanta `NotImplementedError` a propósito, para no aparentar que
  funciona.
- Módulos restantes del §11.2: proyectos, catálogos, programación, estimación,
  materiales, incidencias, cierres, evaluación, cargas, expediente, reportes.
- Cargadores Excel (§9, §10.6) y exportadores.
- Jobs de Arq (CPM, estimación semanal, cargas) y WS/SSE.

## Configuración con RLS — el detalle que importa

El backend **no** usa la *service key* de Supabase ni se conecta como dueño de
las tablas: el owner **salta RLS**. Se conecta con el rol `obractrl_api`
(`database/migrations/0014`) y fija el contexto por transacción:

```sql
SET LOCAL app.org_id = '…';   -- LOCAL: muere con la transacción y no se
SET LOCAL app.usuario_id = '…';  -- filtra a la siguiente petición del pool
SET LOCAL app.rol = 'residente';
```

Por eso los endpoints **nunca reciben `org_id`** (§11.2): el alcance es
implícito y lo impone la base.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # y llenar

pytest tests/domain -q      # dominio puro: no necesita BD
uvicorn obractrl.main:app --reload

# Regenerar el contrato para Orval (§12.8)
curl localhost:8000/api/v1/openapi.json > ../openapi/openapi.json
```

## Despliegue

`render.yaml` define tres servicios: la API web, el worker de Arq y Redis.
El deploy es por Git (§12.8). Las migraciones **no** corren desde aquí: viven
en `database/` y se aplican en el release.
