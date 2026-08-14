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
│  ├─ repos/          repositorios (SQLAlchemy Core, texto parametrizado) + RLS
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
| Repositorios (actividades, obras, calendario, configuración, estimaciones) | `adapters/repos/` | §12.11 |
| Endpoint cableado de punta a punta | `adapters/api/v1/avance.py`, `adapters/api/casos_uso.py` | §11.3 B |
| JWT → contexto RLS | `infrastructure/db/sesion.py`, `adapters/api/dependencias.py` | §12.4 |
| Errores de dominio → problem+json | `main.py` | §11.2 |

**79 pruebas de dominio** (sin BD) + **27 pruebas de integración** (contra
Postgres real, bajo RLS) — ver la sección de pruebas más abajo.

## Lo que falta (siguiente iteración)

- Módulos restantes del §11.2: proyectos, catálogos, programación, estimación,
  materiales, incidencias, cierres, evaluación, cargas, expediente, reportes.
  Sus puertos y repos se agregan igual que `capturar_avance` — es la
  referencia a copiar.
- Cargadores Excel (§9, §10.6) y exportadores.
- Jobs de Arq (CPM, estimación semanal, cargas) y WS/SSE.
- `RecalcularCPM` (o similar): `RepositorioActividades.nodos_cpm_de_obra` /
  `guardar_resultado_cpm` / `marcar_bloqueadas` ya están implementados y
  probados a nivel de repositorio (`tests/integracion/test_actividades_repo.py`),
  pero todavía no tienen un caso de uso que los combine con
  `domain.programacion.cpm.calcular_cpm`.

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

`obractrl_api` (`database/migrations/0014`) nace con `LOGIN` pero **sin
contraseña**: se fija por entorno con
`ALTER ROLE obractrl_api WITH PASSWORD '...'` (nunca en un archivo
versionado) y esa cadena va en `DATABASE_URL`.

## Pruebas

```bash
pytest tests/domain -q      # dominio puro: 79 pruebas, no toca la BD
```

Las de integración (`tests/integracion/`) corren contra un Postgres real con
las migraciones de `database/migrations/` aplicadas, y ejercitan los
repositorios **a través de RLS** (no como superusuario): prueban que el
aislamiento por rol se sostiene en el código Python, no solo en el SQL de
`database/tests/test_rls.sql`.

Requieren dos variables, ninguna con default —no se versionan secretos, ni de
prueba—:

```bash
export DATABASE_URL_ADMIN="postgresql+asyncpg://postgres:...@host:5432/obractrl_test"
export DATABASE_URL_TEST="postgresql+asyncpg://obractrl_api:...@host:5432/obractrl_test"

pytest tests/integracion -v   # 27 pruebas
```

Sin ellas, la carpeta completa se salta (`tests/domain` nunca se ve
afectado). `DATABASE_URL_ADMIN` bypassa RLS a propósito: solo arma y limpia
el escenario de cada prueba; `DATABASE_URL_TEST` es el rol `obractrl_api`,
el mismo que usa el backend en producción — ahí es donde se prueba RLS de
verdad.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env        # y llenar

uvicorn obractrl.main:app --reload

# Regenerar el contrato para Orval (§12.8)
curl localhost:8000/api/v1/openapi.json > ../openapi/openapi.json
```

## Despliegue

`render.yaml` define tres servicios: la API web, el worker de Arq y Redis.
El deploy es por Git (§12.8). Las migraciones **no** corren desde aquí: viven
en `database/` y se aplican en el release.
