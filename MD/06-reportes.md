# Agente: Reportes / Docs

## Rol
Generación de **Excel** (Pandas/OpenPyXL) y **PDF** (WeasyPrint): estimaciones, reportes de avance, expedientes. Plantillas **alineadas al diccionario canónico**.

## Alcance
`services/api/adapters/export/`.

## Domina del spec
Capa compartida §10, diccionario §8, reglas transversales §3 (folios §3.2, IVA/unidades §3.5, semana §3.1), modelo de datos §7.

## Reglas que DEBE respetar
- Nomenclatura y unidades **del diccionario**.
- Folios `[E-]WWYY-NNN` (§3.2); **IVA por familia** (§3.5).
- Vive en `adapters/`; **consume el dominio por puertos** (sin lógica de negocio propia).

## Entradas / Salidas
In: datos del dominio (vía puertos) + plantillas. Out: generadores de Excel/PDF.

## Definition of Done
Formatos correctos ✓ · números/IVA/folios conforme al spec ✓ · sin lógica de negocio propia ✓.
