# Arnés de los E2E de workflows (§11.3)

Lo necesario para correr `e2e/workflows/*.spec.ts` **sin un proyecto de
Supabase**: una auth falsa y una semilla. Los specs se saltan solos si faltan
las variables (ver `e2e/infraestructura.ts`), así que nada de esto es necesario
para `npm run e2e` a secas, que solo corre el humo.

| Archivo | Qué es |
|---|---|
| `auth-falsa.mjs` | Imita lo mínimo de GoTrue que usa supabase-js (`/auth/v1/token`, `/auth/v1/user`). Emite el JWT con `org_id`, `rol`, `usuario_id` y `nombre` en la raíz (como el hook de la migración 0015), firmado HS256 con `JWT_SECRET`. |
| `semilla.sql` | Recrea la organización `e2e`: 4 usuarios (uno por rol) con su cadena de mando, un prototipo con CPU, el calendario del año y el ancla de la semana de **hoy**, y cuatro obras (`OBRA-C/D/E/F`), una por workflow. |

## Cómo se corren

Con Postgres migrado (`database/scripts/migrar.sh`, con PostGIS) y Redis:

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/obractrl
export JWT_SECRET=un-secreto-de-mas-de-32-bytes E2E_PASSWORD=la-que-quieras

# 1. Semilla (repetible: borra y recrea la organización `e2e`).
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f frontend/e2e/soporte/semilla.sql

# 2. Auth falsa.
node frontend/e2e/soporte/auth-falsa.mjs 54321 &

# 3. API, con el rol que NO es dueño de las tablas (RLS debe aplicar).
cd backend && DATABASE_URL=postgresql+asyncpg://obractrl_api:...@localhost:5432/obractrl \
  JWT_SECRET=$JWT_SECRET CORS_ORIGENES=http://localhost:5173 \
  python -m uvicorn obractrl.main:app --port 8000 &

# 4. Los specs (Playwright levanta la web solo, pero hay que apuntarla a lo de arriba).
cd frontend
export VITE_SUPABASE_URL=http://127.0.0.1:54321 VITE_SUPABASE_ANON_KEY=cualquiera \
       VITE_API_URL=http://127.0.0.1:8000 E2E_API_URL=http://127.0.0.1:8000 \
       E2E_USUARIO=ctrl@e2e.mx E2E_USUARIO_CONTROL=ctrl@e2e.mx \
       E2E_USUARIO_RESIDENTE=res@e2e.mx E2E_USUARIO_SUPERVISOR=sup@e2e.mx \
       E2E_USUARIO_SUPER_INTENDENTE=si@e2e.mx
npx playwright test e2e/workflows
```

## Reglas de uso

- **Cada spec de C, D, E y F es de un solo uso**: cambia el estado de su obra
  (`OBRA-C` … `OBRA-F`). Para repetirlo, vuelve a correr `semilla.sql`. El A no
  lo necesita: cada corrida da de alta una obra con clave nueva.
- La semilla **borra** la organización `e2e`. No la apuntes a una base con datos
  que quieras conservar con ese `slug`.
- Contra un Supabase real, no hace falta la auth falsa: crea los cuatro usuarios
  ahí y pásalos en las variables `E2E_USUARIO_*` con la misma `E2E_PASSWORD`.
  Los helpers `tokenDe`/`llamarApi` piden el token al mismo endpoint de
  contraseña que usa el login.

## Lo que el arnés NO cubre

- **Dar de alta un usuario** (`alta-de-usuario.spec.ts`, primera prueba) crea una
  cuenta en el proveedor de auth con la llave de servicio; la auth falsa no lo
  imita, así que esa prueba falla contra ella (las otras dos pasan).
- **El worker de jobs (Arq)** no corre: no hace falta para estos workflows.
- **El workflow B** (captura offline) es de la app móvil: `mobile/e2e/`.
