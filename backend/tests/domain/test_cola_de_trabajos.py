"""Degradación de la cola de trabajos (§12.2 Arq + Redis, §12.8).

`infrastructure/jobs/cola.py` es plomería y se prueba aquí —como
`test_evidencias_r2.py`— porque lo que importa **no** necesita un Redis
levantado: es el contrato de degradación del §12.8.

Un despliegue sin Redis alcanzable no puede responder un 500 opaco. Tiene que
levantar `ColaNoDisponible`, que el borde traduce a 503, con un mensaje que
nombre la variable de entorno y **nunca su valor**: el DSN de Redis puede
traer contraseña (`redis://:pass@host`).
"""

from __future__ import annotations

import pytest

from obractrl.infrastructure.config import Config
from obractrl.infrastructure.jobs.cola import (
    ColaDeTrabajos,
    ColaNoDisponible,
    EstadoTrabajo,
    ResultadoTrabajo,
    TrabajoNoEncontrado,
)

DSN_CON_CONTRASENA = "redis://:contrasena-secreta@redis.interno:6379/0"


def _cola(redis_url: str) -> ColaDeTrabajos:
    return ColaDeTrabajos(Config(redis_url=redis_url))  # type: ignore[arg-type]


class TestSinConfigurar:
    async def test_encolar_sin_redis_url_avisa_cual_variable_falta(self) -> None:
        with pytest.raises(ColaNoDisponible, match="REDIS_URL"):
            await _cola("").encolar("exportar_estimacion_xlsx", obra_id="x")

    async def test_consultar_sin_redis_url_falla_igual(self) -> None:
        """El estado de un reporte y su encolado se degradan parejo: si no hay
        cola, tampoco hay nada que consultar."""
        with pytest.raises(ColaNoDisponible, match="REDIS_URL"):
            await _cola("   ").consultar("abc123")


class TestDsnInvalido:
    async def test_un_dsn_mal_escrito_es_503_y_no_500(self) -> None:
        """La petición es válida; lo que está mal es el entorno (§12.8)."""
        with pytest.raises(ColaNoDisponible, match="DSN"):
            await _cola("no-es-un-dsn").encolar("x")

    async def test_el_mensaje_no_ecoa_la_contrasena_del_dsn(self) -> None:
        """§12.4: el detalle de un `problem+json` sale al cliente."""
        with pytest.raises(ColaNoDisponible) as fallo:
            await _cola("redis://:secreto@:::puerto-malo/0").encolar("x")
        assert "secreto" not in str(fallo.value)


class TestRedisCaido:
    async def test_un_redis_que_no_responde_no_cuelga_la_peticion(self) -> None:
        """`conn_retries=0`: el default de arq son 5 intentos con 1 s de
        espera, y esto corre dentro de una petición HTTP."""
        with pytest.raises(ColaNoDisponible, match="no responde"):
            await _cola("redis://127.0.0.1:1/0").encolar("x")


class TestEstadosQueVeElCliente:
    def test_los_nombres_son_del_dominio_en_espanol(self) -> None:
        """§8.1: el cliente ve `en_cola`, no `queued`."""
        assert (
            EstadoTrabajo.EN_COLA,
            EstadoTrabajo.EN_PROCESO,
            EstadoTrabajo.LISTO,
            EstadoTrabajo.FALLIDO,
        ) == ("en_cola", "en_proceso", "listo", "fallido")

    @pytest.mark.parametrize(
        ("estatus", "listo"),
        [
            (EstadoTrabajo.EN_COLA, False),
            (EstadoTrabajo.EN_PROCESO, False),
            (EstadoTrabajo.FALLIDO, False),
            (EstadoTrabajo.LISTO, True),
        ],
    )
    def test_solo_listo_habilita_la_descarga(self, estatus: str, listo: bool) -> None:
        assert ResultadoTrabajo(id="r1", estatus=estatus).listo is listo

    def test_un_reporte_que_expiro_es_un_404_no_un_500(self) -> None:
        """Arq guarda el resultado un tiempo acotado (`keep_result`); pasado
        eso el reporte deja de existir y hay que volver a pedirlo."""
        assert issubclass(TrabajoNoEncontrado, LookupError)


class TestClaveDeLatido:
    """La llave donde el worker escribe su latido (§11.7).

    Se arma con las constantes de `arq` y no se lee de `RedisSettings`, que
    **no la tiene**: el atributo vive en el `Worker`. Escribirlo mal costaba un
    `AttributeError` que `/health` reportaba como `error: AttributeError` en el
    campo `jobs` — una sonda diciendo «no sé» justo sobre lo que vigila.
    """

    def test_es_la_que_arq_usa(self) -> None:
        from arq.constants import default_queue_name, health_check_key_suffix

        from obractrl.infrastructure.jobs.cola import _clave_de_latido

        assert _clave_de_latido() == f"{default_queue_name}{health_check_key_suffix}"

    def test_los_ajustes_de_conexion_no_la_tienen(self) -> None:
        """Fija el motivo del bug: si algún día `RedisSettings` la expusiera,
        esta prueba avisaría de que se puede simplificar."""
        from arq.connections import RedisSettings

        assert not hasattr(RedisSettings(), "health_check_key")
