# ObraCtrl — Operación

> Qué hacer cuando hay que desplegar, promover, revertir o restaurar.
> Trazabilidad: §12.8 (entornos) · §12.12 (entrega y respaldo) · §11.7 (sondas).

Este documento existe porque la Fase 8 partió de un hallazgo incómodo: **nada
se había desplegado nunca**. Un procedimiento que solo vive en la cabeza de
quien lo escribió no es un procedimiento — y se descubre justo el día que esa
persona no está.

---

## Los dos entornos

| | Staging | Producción |
|---|---|---|
| Rama | `main` | `main` (el mismo commit) |
| Deploy | automático en cada push | **manual**, desde el dashboard |
| Base | proyecto de Supabase propio | proyecto de Supabase propio |
| Redis | propio | propio |
| R2 | bucket propio | bucket propio |
| Correo | sin llaves de Resend | Resend configurado |

No hay una rama `staging`. Una segunda rama de larga vida es lo contrario del
trunk-based del §12.12: staging y prod divergen, y entonces lo que se probó ya
no es lo que se promueve. El commit que se promueve es byte por byte el que
corrió en staging.

---

## Desplegar

### 1 · A staging — no hay nada que hacer

Un push a `main` con CI en verde lo despliega. Después:

```bash
curl https://<staging>/health              # ¿arrancó y con qué versión?
curl https://<staging>/health/dependencias # base, cola, jobs, disco, respaldo
```

`/health/dependencias` dice `estatus: ok` solo si Postgres y Redis responden.
`disco` y `ultimo_respaldo` se reportan pero **no** degradan el estatus: hay que
atenderlos, no despertar a nadie por ellos.

### 2 · Migraciones

Las migraciones **no** corren solas en el deploy, y es a propósito: un contenedor
que migra al arrancar puede migrar dos veces si Render levanta dos instancias, y
un fallo a mitad deja el esquema en un estado que nadie eligió.

```bash
DATABASE_URL="postgresql://...supabase..." ./database/scripts/migrar.sh --estado
DATABASE_URL="postgresql://...supabase..." ./database/scripts/migrar.sh
```

> **La primera vez sobre una base que ya tenía el esquema** (aplicado con el
> runner viejo, que no llevaba control de versión), hay que **sellarla** antes o
> intentaría reaplicarlo todo:
>
> ```bash
> DATABASE_URL=... ./database/scripts/migrar.sh --sellar
> ```

El orden importa y lo fija la regla **expand → contract** (`database/README.md`):
primero se aplica la migración que *agrega*, después se promueve el código, y la
migración que *quita* va en un release posterior. Así el rollback del código
nunca exige rollback de la base.

### 3 · Promover a producción

En el dashboard de Render, sobre `obractrl-api` y `obractrl-worker`: *Manual
Deploy → Deploy a specific commit* y se elige **el commit que ya corrió en
staging**. Los dos, no uno: comparten el esquema de la base, y desplegar solo la
API deja media versión hablando con la otra mitad.

Ese clic es la aprobación del §12.12.

---

## Revertir

### Revertir el deploy

Volver a promover el commit anterior, igual que arriba. Es la vía rápida y no
toca la base — por eso expand → contract importa: si el código anterior tolera
el esquema nuevo, esto basta.

### Revertir una migración

```bash
DATABASE_URL=... ./database/scripts/revertir.sh --pasos 1
```

**Esto borra datos.** Pide confirmación escrita salvo con `--si`. Antes de
correrlo en producción: respaldo, y respaldo probado.

Hay migraciones cuya reversa **no es simétrica**, y cada una lo dice en el
encabezado de su archivo en `database/migrations/down/`. Léelo antes, no después:

- **0017** — la reconciliación de `cant_ejecutada` no tiene número anterior al
  que volver. Y sin su trigger, la captura offline deja de mover el avance en el
  servidor: revertirla con el móvil en campo es perder capturas en silencio.
- **0018** — tirar `actividad.prototipo_nodo_id` pierde el vínculo con el
  prototipo, no solo la columna.
- **0019** — Postgres no tiene `alter type ... drop value`: el valor del enum se
  queda.
- **0021** — las sync rules de PowerSync filtran por esa columna; hay que
  publicar también las reglas anteriores o el móvil deja de sincronizar.
- **0023** — los renglones de bitácora ya escritos **no** se borran. Revertir el
  mecanismo no revierte la historia.

---

## Respaldo

```bash
DATABASE_URL=... ./database/scripts/respaldar.sh /ruta/obractrl-$(date +%F).dump \
  --origen "cron nocturno"
```

Deja constancia en `app.respaldo`, que es de donde `/health/dependencias` saca
`ultimo_respaldo`. El renglón se abre **antes** del `pg_dump` y se cierra
después: un respaldo que se murió a la mitad queda con `ok=false`, que es
justamente lo que hay que poder ver.

### Probar la restauración

```bash
DATABASE_URL=... ./database/scripts/probar_respaldo.sh
```

Respalda, restaura en una base vacía y compara los dos esquemas objeto por
objeto. La comparación es el punto: un `pg_restore` puede terminar en 0 y haber
perdido objetos.

> Un respaldo no probado no es un respaldo. Por eso esto corre en **cada
> corrida de CI** y no solo cuando alguien se acuerda — y por eso `/health`
> reporta las dos fechas por separado: un respaldo de anoche con una
> restauración probada de hace seis meses es exactamente la situación que hay
> que poder ver antes del incidente.

---

## La web no puede hablar con la API (CORS)

El síntoma en el navegador:

```
Access to fetch at 'https://…onrender.com/api/v1/usuarios'
from origin 'https://…vercel.app' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

**El mensaje engaña.** Dice que *falta una cabecera*, que es lo que ve el
navegador; lo que pasó es que el servidor respondió `400 Disallowed CORS
origin` porque ese origen no está en la lista. Se comprueba en un comando:

```bash
curl -i -X OPTIONS https://TU-API.onrender.com/api/v1/usuarios \
  -H "Origin: https://TU-WEB.vercel.app" \
  -H "Access-Control-Request-Method: POST"
```

Y la lista contra la que se comparó la publica la sonda, sin abrir el panel de
Render:

```bash
curl -s https://TU-API.onrender.com/health | jq .cors_origenes
```

**El arreglo** es una variable del servicio web, no un despliegue de código:

```
CORS_ORIGENES=https://control-avance-chi.vercel.app
```

Varios orígenes van separados por comas —la web de producción y la de staging,
por ejemplo—. Después de guardarla, Render reinicia el servicio solo.

Dos cosas que conviene saber antes de pelearse con esto:

- **El dominio de Vercel cambia.** El de producción es estable, pero cada
  *preview deployment* trae su propio subdominio y **no** va a estar en la
  lista. Es correcto que falle: la alternativa —permitir `*.vercel.app`—
  dejaría entrar a la app de cualquiera. Para probar un preview contra la API
  real, se agrega ese origen a mano y se quita después.
- **El default es `http://localhost:5173`**, o sea desarrollo. Un despliegue
  que no fija la variable rechaza a su propia web, que es exactamente lo que
  pasó la primera vez.

### Si el error de CORS aparece **después** de configurar el origen

Entonces ya no es CORS. Un 500 sin manejar se responde por fuera de la pila de
CORS, así que sale sin cabeceras y el navegador reporta lo mismo de siempre —
un error de esquema disfrazado del error que se acaba de arreglar. Pasó aquí:
`GET /usuarios` daba 500 porque la base estaba sin migrar.

Se distingue en un vistazo: **el error de CORS de verdad no trae código de
estado; el disfrazado trae un `500`.**

Desde la Fase 16 el 500 sale con sus cabeceras y su `problem+json`
(`MiddlewareDeErroresConCORS`), así que el navegador muestra el error real. Si
aun así hay dudas, la sonda dice en qué migración está la base:

```bash
curl -s https://TU-API.onrender.com/health/dependencias | jq '.postgres, .esquema'
```

Compáralo con la última del repo:

```bash
ls database/migrations/*.sql | tail -1
```

Si la base va atrás, migra —y **no** selles: `--sellar` marca las migraciones
como aplicadas sin correrlas, y eso solo sirve para una base que ya tiene el
esquema y le falta la bitácora. Sellar una base atrasada la deja rota y
convencida de estar al día.

```bash
cd database
DATABASE_URL="postgresql://…" ./scripts/migrar.sh
```

> **Y revisa `ENTORNO`.** Si vale `dev` —el default— la API publica `/docs` en
> internet con toda su superficie. Con `ENTORNO=prod` se apaga
> (`docs_url=None`, `main.py`). No es urgente, pero no hay motivo para
> regalarlo.

---

## Cuando algo va mal

1. `/health` — ¿el proceso está vivo? Dice versión, entorno y cómo quedó
   configurada la verificación del JWT. Un despliegue sin `SUPABASE_URL` se
   manifiesta como 401 en todas las rutas y aquí se distingue de un token malo.
2. `/health/dependencias` — base, cola, **jobs**, disco y respaldo. `jobs` es el
   que separa "Redis responde" de "hay quien atienda la cola": `SIN WORKER` con
   trabajos encolados es un worker caído, no una cola ocupada.
3. Sentry — API y worker reportan por separado. Un reporte que truena en la cola
   no deja rastro en ninguna respuesta HTTP.
4. `bitacora` — quién cambió qué configuración o catálogo, y cuándo. Es de
   negocio y está separada del log técnico (§11.7): la escribe la base por
   trigger y **nadie puede escribirla a mano ni alterarla**, que es lo que la
   vuelve evidencia.

---

## Al liberar: mover la línea base del contrato (§12.12)

CI verifica en cada PR que el contrato sea **aditivo** respecto de
`openapi/publicado.json`, que es el contrato **que está en producción**. Ese
archivo no se mueve solo: quitar una ruta o volver obligatorio un campo pone el
build en rojo justamente porque la línea base sigue quieta.

Se mueve **una vez, en el commit del release**, junto con el tag `vX.Y.Z`:

```bash
cd backend && python scripts/verificar_compatibilidad.py --publicar
```

Eso declara *este contrato es el que ahora hablan los clientes*. Hacerlo antes
de desplegar apaga la verificación para el cambio que se está por subir, que es
justo cuando sirve.

**Para retirar una ruta** no se borra y ya: se marca con `deprecar(...)`
(`backend/src/obractrl/adapters/api/deprecacion.py`), que le pone su fecha de
retiro en el contrato y manda `Deprecation`/`Sunset` en cada respuesta. Cuando
esa fecha pasa —seis meses por omisión, medidos contra el peor caso: un
teléfono que solo actualiza cuando su dueño entra a Play— se puede quitar y CI
lo acepta.

---

## Actualizar la app móvil sin desplegar (§12.12)

Desde la Fase 15 el móvil pregunta al arrancar qué versión soporta el servidor
(`GET /api/v1/cliente/version`) y manda la suya en cada petición
(`X-Cliente-Version`). Dos variables del servicio web deciden qué pasa:

| Variable | Efecto |
|---|---|
| `MOVIL_VERSION_MINIMA` | Por debajo de esta versión la API responde **426** y la app se bloquea con la pantalla de actualización. |
| `MOVIL_VERSION_RECOMENDADA` | Por debajo de esta, la app solo avisa en "Más". No bloquea nada. |

**Cambiarlas no requiere desplegar código ni publicar en Play.** Es la palanca
que existe para el caso en que un cambio de contrato deje de tolerar a los
clientes viejos: un build nuevo tardaría días en llegar por la tienda, y
llegaría tarde justo a quien ya no puede usar la app.

Por eso el default del código es `0.0.0` —no bloquear a nadie—: dejar gente
afuera tiene que ser una decisión explícita, nunca el efecto de un entorno a
medio configurar.

**Antes de subir la mínima:**

1. Publicar la versión nueva y esperar a que la mayoría actualice. Play
   Console muestra la distribución por `versionCode`; `dispositivo_push`
   guarda `version_app`, que dice lo mismo por usuario activo.
2. Confirmar que el binario nuevo está en la tienda. Bloquear antes de eso
   deja al residente con una pantalla que le pide algo que no existe.
3. Recordar que **lo capturado no se pierde**: la base local y las tres colas
   de salida sobreviven a la actualización (§12.5), y la pantalla de bloqueo
   lo dice con todas sus letras.

Para un fix de JS no hace falta nada de esto: `npm run update` en `mobile/`
publica un OTA de EAS y la app lo descarga sola en el siguiente arranque.
Revertirlo es un rollback de canal, también sin tienda.

---

## Lo que todavía no está

- **Tags `vX.Y.Z` y changelog** (§12.12). Hoy se promueve por commit.
- **Rollback de un deploy real, probado.** La reversión de migraciones y la
  restauración de respaldo sí se prueban en cada corrida de CI; volver a
  promover un commit anterior en Render aún no se ha ejercitado.
