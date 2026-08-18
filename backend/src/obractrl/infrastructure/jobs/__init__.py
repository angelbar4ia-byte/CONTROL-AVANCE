"""Jobs con Arq + Redis (§12.2).

`cola.py` encola y consulta; las funciones que corren viven en
`adapters/export/trabajos.py` y el proceso worker las ensambla en
`obractrl/trabajador.py`. La infraestructura no importa `adapters`: la
composición es del borde (§12.11).
"""
