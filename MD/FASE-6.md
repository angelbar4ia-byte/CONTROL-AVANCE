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
| 3 | `Idempotency-Key` en mutaciones sensibles (§11.2, §12.3) | **backend hecho**, falta cablearlo en las pantallas | tabla `idempotencia` + dependencia |
| 4 | Sync rules de PowerSync auditadas contra RLS (§12.4, §12.5) | **hecho** | auditoría + `registro_avance.obra_id` |
| 5 | E2E Playwright de los seis workflows (§11.3) | pendiente | — |
| 6 | Despliegue: Render · Vercel · Play Store (§12.8, §12.13) | **hecho** | CI y worker de Render corregido |

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

**Decidido: tabla en Postgres, no Redis.** La clave y la mutación tienen que
quedar en la **misma transacción**. Con Redis no pueden: entre el `COMMIT` en
Postgres y el `SET` en Redis hay una ventana, y un proceso que muere ahí deja
la mutación aplicada y la clave sin registrar — que es exactamente el caso que
la idempotencia existe para cubrir. Redis además no es durable aquí: un
reinicio borraría las claves y el reintento posterior duplicaría.

**Entregado (backend).** Migración 0022 (`idempotencia`) y
`adapters/api/idempotencia.py`. La dependencia corre antes del endpoint sobre
**la misma sesión** que usará el caso de uso, así que su `insert` viaja en la
transacción que `UnidadDeTrabajoSQL.commit()` cierra: o quedan la clave y el
cierre, o no queda ninguno. Hay prueba de las dos direcciones —commit y
rollback— en `tests/integracion/test_idempotencia_endtoend.py`.

Las **10 mutaciones sensibles** protegidas son las que mueven dinero o dejan
estado irreversible: los cuatro pasos del workflow C (solicitar, autorizar,
validar, rechazar cierre), los tres del E (generar, enviar, validar
estimación), la salida de almacén y las dos altas masivas (`/obras/bulk`,
`/obras/{id}/generar`). Hay una prueba que fija esa lista exacta contra el
contrato, para que agregar una mutación sensible sin protegerla se note.

Respuestas: misma clave y misma huella → **409** (`peticion-ya-procesada`);
misma clave con otra petición → **422**, porque es un error del cliente y no un
reintento. El choque de `uq_idempotencia` se traduce también a 409: dos
peticiones idénticas **en paralelo** —el doble clic— no las cubre el `select`
previo, y ahí la unicidad de la base es la que decide.

**Lo que este diseño NO hace.** No guarda la respuesta original para
devolverla en el reintento. Guardarla obligaría a escribirla *después* del
commit —la respuesta no existe antes—, o sea en una segunda transacción, y un
fallo justo ahí dejaría una clave sin respuesta: el reintento tendría que
contestar 409 igual. Se prefiere contestar 409 siempre. El invariante que
importa, que la operación ocurra exactamente una vez, se cumple entero; el
cliente que necesite el cuerpo vuelve a consultar el recurso.

### Lo que falta: cablearlo en las pantallas

Orval **no** generó el parámetro de cabecera con la configuración actual, así
que los hooks generados no lo pasan. Y el punto fino: **la clave la tiene que
fijar quien llama**, una vez por operación. Una generada dentro de `peticion`
cambiaría en cada intento y no desduplicaría nada — sería teatro.

Hecho en el front: `claveDeIdempotencia()` en `api/cliente.ts` (el transporte
ya reenvía `config.headers`, así que la pass-through funciona) y el comentario
de `queryClient.ts` corregido, porque afirmaba que las mutaciones ya llevaban
la cabecera y no era cierto.

Falta: que cada pantalla que dispara una de las 10 mutaciones cree su clave al
montar el formulario y la mande en cada intento. Ahí se puede volver a
encender `retry` en las mutaciones, que hoy está en 0 justamente por esto.

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

### La auditoría

El invariante que se verifica es **asimétrico**: sincronizar *menos* de lo que
RLS permite es una decisión de producto; sincronizar *más* es una fuga. Así que
por cada tabla la pregunta es "¿el bucket cabe dentro de lo que la política
dejaría leer?".

De las **53 tablas con RLS**, el móvil sincroniza **7**. Las demás no se
excluyen por descuido:

| Grupo | Tablas | Por qué no sincroniza |
|---|---|---|
| Catálogos de costo | `unidad`, `familia`, `insumo`, `cpu`, `explosion`, `presupuesto`, `partida_presupuesto`, `grupo_funcional*`, `mapeo`… | El costo es web (§5.2: "toda la configuración es solo web"). Meter el CPU en cada teléfono sería pesado y no lo usa ninguna pantalla de campo. |
| Programación | `programa_base*`, `programa_obra`, `prototipo*`, `nivel`, `etapa_constructiva`, `calendario`, `ancla_semana` | La ruta crítica se **consulta** en móvil (§5.2 tab *Ruta*) pero se calcula en el servidor: se lee por API, no por réplica. |
| Flujos que exigen estar en línea | `estimacion*`, `solicitud_cierre`, `cierre_obra*`, `evaluacion*`, `periodo_bloqueado` | Son transiciones con folio, validación por rol y efectos (§11.3 C, E, H). Resolverlas last-write-wins offline produciría dobles folios y dobles cobros. |
| Cargas y soporte | `carga_datos`, `carga_snapshot`, `pendiente`, `expediente_doc`, `evidencia`, `bitacora`, `notificacion`, `proceso` | `es_config()` en su política: son de Control/SI en web. |
| Identidad y alcance | `usuario`, `organizacion`, `supervisor_cluster`, `control_proyecto`, `proyecto`, `cluster` | Se leen en las *parameter queries* para resolver el bucket; no hacen falta como datos en el dispositivo. |

Lo que **sí** sincroniza, y contra qué política se comparó:

| Tabla | Alcance del bucket | Política RLS espejada | ¿Cabe? |
|---|---|---|---|
| `frente`, `concepto` | `org_id` del usuario | loop `catalogos`: `org_id = current_org_id()` | sí, y más estrecho: solo `concepto.estatus = 'activo'` y 4 columnas |
| `obra` | `obra.id = bucket.obra_id` | `obra_select` vía `obra_visible()` | sí: el bucket **es** `obra_visible` |
| `actividad`, `incidencia`, `revision_fisica` | `obra_id = bucket.obra_id` | loop `por_obra`: `org + obra_visible(obra_id)` | sí, idéntico |
| `registro_avance` | `obra_id = bucket.obra_id` | `registro_avance_scope`: `org + obra_visible(actividad.obra_id)` | sí — ver abajo |

### Lo que estaba mal

**1. `registro_avance` no se podía sincronizar.** Su regla era

    SELECT * FROM registro_avance
     WHERE actividad_id IN (SELECT id FROM actividad WHERE obra_id = ...)

y las *data queries* de PowerSync filtran contra los parámetros del bucket y
nada más: no admiten `join` ni subconsulta. `registro_avance` llega a la obra
por su actividad (§7.6) y no tenía `obra_id`. Y es **la tabla que más se
escribe offline**: es la bitácora de captura del residente y la fuente de
`actividad.cant_ejecutada` desde la migración 0017 — o sea, el workflow B
entero.

Arreglado con la **migración 0021**: `registro_avance.obra_id`, derivada por
trigger desde `actividad.obra_id`. Tres cosas que la hacen segura:

- **El trigger pisa lo que venga en el insert.** El escritor de esta tabla es
  un teléfono que escribe directo a Postgres (D5); si el valor se aceptara tal
  cual, un cliente podría marcar su captura como de otra obra.
- **La política RLS no cambió.** Sigue autorizando por `actividad_id`, que es
  el dato que el cliente tiene que acertar para que la fila signifique algo.
  `obra_id` es copia derivada para sincronizar e indexar, no fuente de
  autorización.
- **Sigue a la actividad en los `UPDATE`**, para que una corrección no deje la
  captura en el bucket equivocado.

`database/tests/test_registro_avance_obra.sql` cubre los tres casos más el
aislamiento.

**2. `SELECT *` en todas las data queries.** Se cambió por listas explícitas
que coinciden con `mobile/src/sync/powersync.ts`. El argumento no es de estilo:
con `*`, el día que una migración le agregue una columna a `obra` —un costo,
una nota interna— esa columna sale hacia todos los teléfonos sin que nadie lo
decida. La lista explícita convierte "qué sale del servidor" en algo que se
revisa en un diff.

**3. Los joins de alcance no filtraban `org_id`.** `supervisor_cluster` y
`control_proyecto` se unían solo por `usuario_id`. No era explotable —un
`usuario.id` pertenece a una sola organización y la obra sí filtraba por
`u.org_id`—, pero la defensa dependía de un invariante implícito en vez de
estar escrita. Ahora las tres uniones llevan su `org_id`.

### Lo que se deja anotado y no se cambia

§5.2 le da al supervisor un tab de *Cierres* en móvil, y `solicitud_cierre` no
sincroniza. Es deliberado: autorizar un cierre es una transición con efectos
(§11.3 C) y resolverla last-write-wins offline dejaría cierres autorizados dos
veces. El tab funciona en línea contra la API. Si algún día tiene que ver
cierres sin señal, va como bucket **de solo lectura**, nunca como cola de
escritura.

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

**Entregado.**

**El worker de Render no habría arrancado.** `render.yaml` lo lanzaba con
`arq obractrl.infrastructure.jobs.worker.Configuracion`, un módulo que no
existe: el composition root de los jobs es `obractrl/trabajador.py`
(`WorkerSettings`), hermano de `main.py`. Con eso, el servicio worker habría
fallado al arrancar y **todos los reportes se habrían quedado encolados sin
que nadie los procesara** — y el síntoma del lado del usuario sería un reporte
eternamente `en_cola`, no un error.

Además: `RESEND_API_KEY`/`RESEND_REMITENTE` en el servicio web (van ahí y no en
el worker: el bus de eventos es en proceso, §11.1) y `SENTRY_DSN` en el worker,
que hasta ahora no reportaba a ningún lado —un reporte que truena en la cola no
deja rastro en ninguna respuesta HTTP—.

**CI, por primera vez.** `.github/workflows/ci.yml` con tres jobs. Lo que
justifica el archivo no es correr lo que ya corre en local, sino que **levanta
Postgres**: sin él, `backend/tests/integracion/` se salta entero —su
`conftest.py` lo declara así— y los archivos de `database/tests/` no corren
nunca. Son ~150 pruebas y 5 archivos de aislamiento RLS que hasta hoy solo se
ejercitaban a mano. Se apoya en que la migración 0014 crea `anon`,
`authenticated` y `obractrl_api` en un Postgres pelón justo para esto.

Incluye un paso que **verifica que `openapi.json` esté al día**: regenera el
contrato y lo compara contra el versionado. Si alguien cambia un endpoint y no
regenera, el front programa contra un contrato viejo (§12.2) y hoy nada lo
detectaba.

`vercel.json` y `eas.json` ya estaban completos —incluido el flujo de §12.13
con `track: internal` y `releaseStatus: draft`—; no hizo falta tocarlos.

**No verificado aquí:** el workflow no se ha ejecutado nunca. Cada comando es
uno que ya corre en local, y el YAML y el heredoc del paso de contrato se
validaron parseándolos, pero la primera corrida real es la que dirá si el
servicio de Postgres y los `working-directory` quedaron bien.

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

**F6.6 · Sincronizar menos que RLS está bien; sincronizar más, nunca.** El
invariante del §12.4 es asimétrico y así se auditó: por cada tabla la pregunta
fue si el bucket cabe dentro de lo que la política dejaría leer, no si coincide
exactamente. Por eso `concepto` puede sincronizar 4 columnas y solo las activas
sin que eso sea una divergencia.

**F6.7 · `registro_avance.obra_id` es derivada, no declarada.** La escribe un
trigger que pisa lo que mande el cliente, y la autorización sigue resolviéndose
por `actividad_id`. Una columna que existe para sincronizar no puede volverse
la que decide quién ve qué: si el cliente pudiera fijarla, marcaría sus
capturas como de cualquier obra.

**F6.8 · El paso de CI que compara el contrato no es burocracia.** `openapi.json`
lo consume Orval para generar los hooks del front y del móvil (§12.2). Un
endpoint cambiado sin regenerar no rompe ninguna prueba —el front sigue
compilando contra el contrato viejo— y se descubre en producción. Compararlo en
CI es lo único que convierte "el front programa contra el contrato" en algo
verificado y no en una costumbre.

**F6.9 · La clave de idempotencia va en Postgres porque tiene que ser atómica
con la mutación.** Es la única razón; si no fuera por eso, Redis era más
barato y ya estaba. Ver el frente 3.

**F6.10 · Una clave por operación, no por petición.** Es la parte que se puede
implementar mal sin notarlo: generar la clave dentro del transporte HTTP da
una cabecera nueva en cada intento y no desduplica nada. Por eso el front
expone `claveDeIdempotencia()` para que la fije quien dispara la mutación, en
vez de mandarla sola desde `peticion`.
