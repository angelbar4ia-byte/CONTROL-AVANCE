"""Firma de URLs para subir evidencias a R2 (§11.2, §12.2, §12.4).

Vive en `infrastructure/storage/r2.py` y no en `domain/`, pero se prueba aquí
—igual que `test_eventos.py`— porque es puro: `generate_presigned_url` calcula
un HMAC sobre credenciales que ya están en memoria y **no hace red**, así que
no necesita ni Postgres ni un bucket real.

Lo que se verifica es el contrato del §12.4: el secreto de R2 no sale nunca en
la URL firmada, la clave del objeto la decide el servidor con el `org_id` del
token (y no el cliente), y un despliegue sin credenciales falla con un error
nombrado —no con un 500 opaco ni, peor, con una URL que reventaría recién en
el `PUT` del móvil.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from obractrl.infrastructure.config import Config
from obractrl.infrastructure.storage.r2 import (
    AlmacenamientoNoConfigurado,
    clave_de_evidencia,
    firmar_subida,
)

ACCESS_KEY = "AKIAOBRACTRLDEPRUEBA"
SECRET_KEY = "secreto-de-prueba-que-jamas-debe-salir-en-una-respuesta"


def _config(**cambios: str) -> Config:
    valores: dict[str, str] = {
        "r2_endpoint": "https://cuenta.r2.cloudflarestorage.com",
        "r2_bucket": "obractrl-evidencias",
        "r2_access_key": ACCESS_KEY,
        "r2_secret_key": SECRET_KEY,
    }
    valores.update(cambios)
    return Config(**valores)  # type: ignore[arg-type]


class TestSinCredenciales:
    @pytest.mark.parametrize(
        ("campo", "variable"),
        [
            ("r2_endpoint", "R2_ENDPOINT"),
            ("r2_bucket", "R2_BUCKET"),
            ("r2_access_key", "R2_ACCESS_KEY"),
            ("r2_secret_key", "R2_SECRET_KEY"),
        ],
    )
    def test_falla_nombrando_la_variable_que_falta(
        self, campo: str, variable: str
    ) -> None:
        """Un despliegue a medias (§12.8) debe verse como tal, no como un 500."""
        with pytest.raises(AlmacenamientoNoConfigurado, match=variable):
            firmar_subida(
                clave="org/foto.jpg",
                content_type="image/jpeg",
                cfg=_config(**{campo: ""}),
            )

    def test_el_error_no_incluye_el_valor_de_ninguna_credencial(self) -> None:
        with pytest.raises(AlmacenamientoNoConfigurado) as exc:
            firmar_subida(
                clave="org/foto.jpg",
                content_type="image/jpeg",
                cfg=_config(r2_endpoint=""),
            )
        assert SECRET_KEY not in str(exc.value)
        assert ACCESS_KEY not in str(exc.value)


class TestLaFirmaNoExponeCredenciales:
    def test_el_secreto_no_aparece_en_la_url(self) -> None:
        """Lo que viaja es un HMAC derivado del secreto, no el secreto: de la
        firma no se puede volver a la llave (§12.4)."""
        firma = firmar_subida(
            clave="org/foto.jpg", content_type="image/jpeg", cfg=_config()
        )
        assert SECRET_KEY not in firma.url

    def test_el_secreto_no_aparece_en_ningun_campo_de_la_respuesta(self) -> None:
        firma = firmar_subida(
            clave="org/foto.jpg", content_type="image/jpeg", cfg=_config()
        )
        serializado = repr(firma)
        assert SECRET_KEY not in serializado

    def test_el_access_key_id_si_va_en_la_credencial_de_sigv4(self) -> None:
        """Es inevitable y es correcto: SigV4 le dice a R2 con qué llave
        verificar, como un JWT dice su `kid`. Sin el secreto no abre nada — se
        afirma explícitamente para que nadie lo "arregle" creyéndolo una fuga.
        """
        firma = firmar_subida(
            clave="org/foto.jpg", content_type="image/jpeg", cfg=_config()
        )
        query = parse_qs(urlparse(firma.url).query)
        assert query["X-Amz-Credential"][0].startswith(ACCESS_KEY)
        assert "X-Amz-Signature" in query

    def test_la_url_caduca(self) -> None:
        firma = firmar_subida(
            clave="org/foto.jpg",
            content_type="image/jpeg",
            cfg=_config(),
            expira_en=timedelta(minutes=5),
        )
        query = parse_qs(urlparse(firma.url).query)
        assert query["X-Amz-Expires"][0] == "300"
        assert firma.expira_en_segundos == 300
        assert firma.expira_en > datetime.now(UTC)

    def test_apunta_al_bucket_y_a_la_clave_pedidos(self) -> None:
        firma = firmar_subida(
            clave="org/obras/foto.jpg", content_type="image/jpeg", cfg=_config()
        )
        assert "obractrl-evidencias" in firma.url
        assert "org/obras/foto.jpg" in urlparse(firma.url).path
        assert firma.metodo == "PUT"
        assert firma.clave == "org/obras/foto.jpg"


class TestClaveDeEvidencia:
    def test_la_clave_empieza_por_la_organizacion(self) -> None:
        """R2 no tiene RLS: el prefijo por `org_id` es la frontera equivalente
        (§12.4). El `org_id` sale del token, no de la petición."""
        org = uuid.uuid4()
        clave = clave_de_evidencia(org_id=org, nombre_archivo="foto.jpg")
        assert clave.startswith(f"{org}/")

    def test_agrupa_por_obra_cuando_se_indica(self) -> None:
        org, obra = uuid.uuid4(), uuid.uuid4()
        clave = clave_de_evidencia(
            org_id=org, nombre_archivo="foto.jpg", obra_id=obra
        )
        assert clave.startswith(f"{org}/obras/{obra}/")

    def test_un_nombre_con_ruta_no_escapa_del_prefijo(self) -> None:
        """Sin sanear, un `../` en el nombre sacaría el objeto del espacio de
        su organización — justo lo que el prefijo evita."""
        org = uuid.uuid4()
        clave = clave_de_evidencia(
            org_id=org, nombre_archivo="../../otra-org/secreto.jpg"
        )
        assert clave.startswith(f"{org}/")
        assert ".." not in clave
        assert clave.count("/") == 2  # org / uuid / nombre

    def test_saneado_de_acentos_y_espacios(self) -> None:
        clave = clave_de_evidencia(
            org_id=uuid.uuid4(), nombre_archivo="Cimentación norte (1).JPG"
        )
        assert clave.endswith("Cimentacion-norte-1-.JPG")

    def test_un_nombre_que_se_queda_sin_nada_usable_no_deja_la_clave_colgando(
        self,
    ) -> None:
        clave = clave_de_evidencia(org_id=uuid.uuid4(), nombre_archivo="///")
        assert clave.endswith("/evidencia")

    def test_dos_subidas_del_mismo_nombre_no_se_pisan(self) -> None:
        org = uuid.uuid4()
        primera = clave_de_evidencia(org_id=org, nombre_archivo="foto.jpg")
        segunda = clave_de_evidencia(org_id=org, nombre_archivo="foto.jpg")
        assert primera != segunda


class TestFirmarDescarga:
    def test_firma_un_get_sin_exponer_el_secreto(self) -> None:
        from obractrl.infrastructure.storage.r2 import firmar_descarga

        firma = firmar_descarga(clave="org/planos/pb.png", cfg=_config())
        query = parse_qs(urlparse(firma.url).query)
        assert "org/planos/pb.png" in firma.url
        assert "X-Amz-Signature" in query
        assert SECRET_KEY not in firma.url

    def test_sin_credenciales_falla_nombrando_la_variable(self) -> None:
        from obractrl.infrastructure.storage.r2 import firmar_descarga

        with pytest.raises(AlmacenamientoNoConfigurado, match="R2_SECRET_KEY"):
            firmar_descarga(clave="org/planos/pb.png", cfg=_config(r2_secret_key=""))
