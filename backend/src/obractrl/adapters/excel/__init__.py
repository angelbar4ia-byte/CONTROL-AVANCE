"""Cargadores por archivo del §10.6 y sus plantillas.

Spec §9 (cargadores) · §10.2 (modos y pipeline) · §10.6 (cabeceras) ·
§12.11 (`adapters/excel`: cargadores por archivo + 3 modos).

Aquí vive **todo** el trato con el `.xlsx`: abrirlo con límites
(`lector`), recorrerlo y mapear columnas (`pipeline`), atar cada archivo con
su validador (`cargadores`) y generar la plantilla descargable
(`plantillas`). Las reglas —qué columnas exige el contrato, qué hace válida a
una fila, qué diferencia hay contra lo vigente— están en
`domain.cargadores`, que no importa openpyxl ni pandas (§12.11).
"""
