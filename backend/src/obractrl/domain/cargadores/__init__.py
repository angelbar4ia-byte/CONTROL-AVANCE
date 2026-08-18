"""Dominio de los cargadores de datos.

Spec §9 (cargadores) · §10.2 (modos y pipeline) · §10.3 (mapeos y bandeja) ·
§10.6 (cabeceras canónicas) · §10.8 (versionado y reversa).

Aquí viven las **reglas** de una carga: qué columnas exige cada archivo, qué
hace válida a una fila, qué cae en la bandeja de pendientes y qué diferencia
hay entre lo que trae el archivo y lo que ya está vigente. Leer el `.xlsx`
—abrirlo, recorrer hojas, resolver celdas— es del borde (`adapters/excel`,
§12.11): este paquete no importa pandas ni openpyxl y se prueba sin tocar
disco.
"""
