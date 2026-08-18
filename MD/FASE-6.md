# Fase 6 — Endurecimiento y despliegue · bitácora de avance

> **Para retomar:** este archivo es el estado real de la fase. Cada frente dice
> qué se entregó, qué falta y **por qué** se decidió lo que se decidió. Si la
> sesión se interrumpe, empezar leyendo la tabla de abajo y el frente marcado
> como *en curso*.

**Fuente de verdad:** [`ObraCtrl-especificacion-tecnica.md`](ObraCtrl-especificacion-tecnica.md)
· **Plan:** [`ROADMAP.md`](ROADMAP.md) (Fase 6) · **Contrato:** [`AGENTS.md`](AGENTS.md).

El roadmap resume la fase en tres renglones. Desglosados son **seis frentes**
independientes entre sí, así que se entregan de uno en uno y cada uno se
commitea solo. Ninguno bloquea a otro.

## Tablero

| # | Frente | Estado | Commit |
|---|---|---|---|
| 1 | `problem+json` uniforme (§11.2) | **hecho** | `problem+json` en todo error |
| 2 | Observabilidad: Sentry, request id, logs separados (§11.7) | **hecho** | id de petición, Sentry y sonda de dependencias |
| 3 | `Idempotency-Key` en mutaciones sensibles (§11.2, §12.3) | pendiente | — |
| 4 | Sync rules de PowerSync auditadas contra RLS (§12.4, §12.5) | pendiente | — |
| 5 | E2E Playwright de los seis workflows (§11.3) | pendiente | — |
| 6 | Despliegue: Render · Vercel · Play Store (§12.8, §12.13) | pendiente | — |

---

## 1 · `problem+json` uniforme

**Qué pide el spec.** §11.2: "Errores en **problem+json** (RFC 7807)".

**Dónde está hoy.** `main.py` traduce ~40 excepciones de dominio con el helper
`_problema`, y eso está bien. Lo que **no** pasa por ahí:

- `HTTPException` de los routers —el 403 de `exigir_rol`, el 409 de
  `/reportes/{id}/descargar`— sale con el `{"detail": ...}` por defecto de
  FastAPI y `content-type: application/json`.
- `RequestValidationError` (422 de Pydantic) sale con el formato de FastAPI.
- Una excepción no manejada sale como 500 de texto plano.

El front ya asume RFC 7807 en **todas** las respuestas de error
(`frontend/src/api/cliente.ts` lee `type`/`title`/`detail`), así que hoy los
tres casos de arriba le llegan degradados.

**Criterio de cierre.** Ninguna respuesta de error de la API sale sin
`application/problem+json`. Prueba que recorra los tres casos.

**Entregado.** Tres manejadores genéricos al final de
`_registrar_manejadores_de_error`: `HTTPException` de Starlette (cubre también
la de FastAPI, que hereda de ella, y con eso los 404/405 de enrutamiento),
`RequestValidationError` y un `Exception` de último recurso. 15 pruebas en
`backend/tests/api/test_problem_json.py`, sin Postgres —estas rutas fallan en
el borde—.

Tres cosas que valen más que la uniformidad en sí:

- El 422 de Pydantic **conserva qué campo falló** en `errores[]`. Uniformar el
  formato no puede costar el detalle por campo: el front lo necesita para
  marcar el input.
- El 500 **no devuelve `str(exc)`**. El mensaje de un fallo no previsto puede
  traer SQL, una ruta del servidor o el valor de la fila en proceso (§12.4).
  Va la clase de la excepción, que es lo que permite cruzar el reporte del
  usuario con el log; la traza completa se registra, no se responde.
- El manejador de `HTTPException` **copia las cabeceras**. Sin eso, el 401
  perdía su `WWW-Authenticate: Bearer`.

**Defecto encontrado de paso.** Una petición **sin** cabecera `Authorization`
respondía **403 "Not authenticated"** —el default de `HTTPBearer(auto_error=True)`—
en vez de 401. Dice lo contrario de lo que pasa: 403 es "te identifiqué y no
puedes", y ahí nadie se identificó. Un front que distingue "manda a login" de
"muestra no tienes permiso" —el nuestro lo hace— enseñaba la pantalla
equivocada. Corregido con `auto_error=False` y el 401 explícito en
`contexto_actual`.

## 2 · Observabilidad

**Qué pide el spec.** §11.7 (citado en §12): "**health** (BD/API/disco/último
respaldo/jobs); **logs separados** (bitácora de negocio vs log técnico)".
§12.2 nombra Sentry.

**Dónde está hoy.** `Config.sentry_dsn` existe y **no lo usa nadie**.
`/health` ya sonda JWT/JWKS/ES256 (bien: nació de un incidente real) pero no
dice nada de la BD ni de la cola. No hay id de petición: un 500 en Render no
se puede cruzar con la petición que lo produjo.

**Criterio de cierre.** Sentry inicializado si hay DSN (y silencioso si no,
como Resend); `X-Request-Id` que entra o se genera y viaja al log y al
`problem+json`; `/health` con el estado de Postgres y Redis sin volverse una
ruta cara.

**Entregado.** `infrastructure/observabilidad.py` (ContextVar del id, filtro y
formato de log, arranque de Sentry) y `adapters/api/middleware.py` (la cabecera).
27 pruebas en `backend/tests/api/test_observabilidad.py`.

- **El id cose las tres cosas**: sale en `X-Request-Id`, en `request_id` del
  `problem+json` (RFC 7807 §3.2 permite extensiones) y en cada línea de log.
  Se respeta el que traiga el cliente —para seguir una petición a través de
  los servicios— y se sanea: un id con saltos de línea inyectaría renglones
  falsos en la bitácora.
- **`expose_headers` en CORS**: sin eso el navegador no deja leer el id justo
  cuando el front lo necesita, que es en la respuesta de error que va a
  reportar.
- **`sqlalchemy.engine` fijado en WARNING**, incluso en debug: en INFO registra
  cada sentencia **con sus parámetros**, y esos parámetros son datos de la
  organización (§12.4).
- **La sonda se partió en dos.** `/health` sigue sin tocar nada —es la de
  liveness de Render; si la base se cae, reiniciar el proceso solo agrega un
  arranque en frío a un incidente que ya existe— y `/health/dependencias`
  consulta Postgres y Redis en paralelo, con 3 s por dependencia. **Nunca
  responde 5xx**: una sonda que se cae junto con lo que vigila no diagnostica
  nada. Reporta la clase del fallo, nunca la cadena de conexión.

**Deuda que salió a la luz.** `RESEND_API_KEY` y `RESEND_REMITENTE` (Fase 5) no
estaban ni en `.env.example` ni en `render.yaml`. Se agregaron al primero; el
segundo se atiende en el frente 6 junto con el worker de jobs.

## 3 · `Idempotency-Key`

**Qué pide el spec.** §11.2: "Mutaciones sensibles con `Idempotency-Key`".
§12.3 lo nombra para cargas, donde **ya existe** por hash de archivo
(`gestionar_carga.py`) — ese caso está resuelto y no se toca.

**Dónde está hoy.** Nada en HTTP. El front ya desactivó el reintento de
mutaciones por esto (`queryClient.ts` lo dice en un comentario), o sea que hoy
se paga el costo sin tener el beneficio.

**Qué falta decidir al empezar.** Dónde vive la clave: tabla en Postgres
(sobrevive al reinicio, entra en la transacción, cuesta una migración) o Redis
(ya está para los jobs, se pierde al reiniciar). Y **cuáles** son las
mutaciones sensibles: como mínimo las que mueven dinero o estado irreversible
—solicitar/validar cierre, generar/validar estimación, salida de almacén—.

## 4 · Sync rules ↔ RLS

**Qué pide el spec.** §12.4: "las sync rules de PowerSync deben reflejar el
mismo `org_id`/rol que las políticas RLS, para que el offline no exponga datos
de otra org". Es el invariante 3 del roadmap.

**Dónde está hoy.** `mobile/sync-rules.yaml` existe y espeja `app.obra_visible`
para los tres roles móviles. **Se escribió en la Fase 1** y desde entonces las
fases 2–5 agregaron tablas; hace falta auditarlo tabla por tabla contra
`0011_rls_helpers.sql` y `0012_rls_policies.sql`.

**Criterio de cierre.** Una auditoría escrita —qué tabla sincroniza, con qué
alcance y por qué las demás no— y, si hay divergencia, corregida.

## 5 · E2E Playwright

**Qué pide el spec / roadmap.** Los seis workflows del §11.3 (A generar obra ·
B captura offline · C cierre · D cierre de obra · E estimación · F incidencia).

**Dónde está hoy.** Playwright está en `devDependencies` y hay script
`npm run e2e`, pero **no existe** ni `playwright.config.ts` ni carpeta `e2e/`.

**Nota de realidad.** Un E2E de verdad necesita API + Postgres + sesión
Supabase levantados. En una máquina sin esa infra los specs se escriben pero
no se pueden correr; hay que dejar dicho cómo se corren en vez de fingir que
pasan.

## 6 · Despliegue

**Qué pide el spec.** §12.8 (entornos y CI/CD) y §12.13 (publicación en Play).

**Dónde está hoy.** `backend/render.yaml` existe; el worker de jobs
(`obractrl.trabajador`) es **nuevo de la Fase 5** y hay que ver si está
declarado ahí. `mobile/eas.json` existe. No hay workflows de CI en `.github/`,
así que "verde en CI" es hoy una promesa sin CI.

**Confirmado al pasar por el frente 2:** `render.yaml` **no** declara
`RESEND_API_KEY` ni `RESEND_REMITENTE`. Revisar de paso si declara el worker.

---

## Decisiones de la fase

**F6.1 · El slug de `type` existe siempre, aunque el error no sea de dominio.**
Los errores de regla traen nombre propio (`regla-de-cierre`,
`estimacion-no-encontrada`) porque el cliente ramifica sobre ellos. Los de
protocolo no tienen nada sobre qué ramificar, pero igual llevan slug
(`no-autenticado`, `conflicto`, `error-interno`): el front lee `type` en toda
respuesta de error, y un `undefined` ahí es un caso especial de más en el
cliente. El slug describe el estado y ya.

**F6.2 · Se atrapa la `HTTPException` de Starlette, no la de FastAPI.** La de
FastAPI hereda de ella, así que atrapar la de Starlette cubre las dos; al
revés se quedaban fuera los 404 y 405 que enruta Starlette sola, antes de que
exista un router.

**F6.3 · Liveness y readiness son dos rutas, no una.** `/health` responde sin
tocar nada porque es lo que Render sondea para decidir si reinicia: una sonda
que falla cuando falla Postgres convertiría una caída de base en un ciclo de
reinicios. `/health/dependencias` es la que consulta, y responde 200 siempre —
con el estado de cada dependencia en su campo— para que un monitor alerte sobre
el campo y no sobre el código HTTP.

**F6.4 · El id de petición se recorta, no se descarta.** Un `X-Request-Id`
larguísimo se corta a 64 caracteres en vez de reemplazarse: el prefijo del id
del cliente sigue sirviendo para correlacionar, y el riesgo real —una cabecera
de 8 KB repetida en cada línea de log— ya quedó acotado. Solo se reemplaza el
que trae caracteres que no sirven, porque ahí sí hay riesgo de inyección en la
bitácora.

**F6.5 · Middleware ASGI puro, no `BaseHTTPMiddleware`.** El de Starlette corre
el endpoint en otra tarea, así que el `ContextVar` que fija el middleware
podría no ser el que ve el endpoint. Hay una prueba que compara el id que ve el
endpoint contra el que sale en la cabecera, justo por esto.
