# `openapi/`

Contrato de la API. FastAPI genera `openapi.json` y Orval genera desde aquí
los hooks de TanStack Query para web y móvil (§12.2).

Se regenera en CI en cada cambio de contrato (§12.8):

```bash
cd backend && uvicorn obractrl.main:app &
curl localhost:8000/api/v1/openapi.json > ../openapi/openapi.json
cd ../frontend && npm run api:generar
```

El front programa **contra el contrato**, no contra la implementación: un
cambio interno del backend no rompe el front mientras el contrato se respete.
