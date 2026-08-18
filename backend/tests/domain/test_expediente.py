"""Expediente técnico de la obra (§7.9, §11.2 "Expediente").

Dos piezas puras, probadas juntas porque son las dos mitades del mismo
contexto:

- `domain.expediente.reglas` — quién sube un documento y con qué datos.
- `domain.reportes.expediente` — el agregado que reúne documentos, evidencias,
  cierres y estimaciones, y que alimenta **con los mismos números** la vista
  JSON (`GET /obras/{id}/expediente/vista`) y el PDF (`adapters/export/pdf`).

Lo que se fija aquí es lo que el §11.3 D necesita del expediente para sostener
un cierre de obra: que solo sume lo **validado** y que cada evidencia diga de
dónde salió.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from obractrl.domain.expediente.reglas import (
    ROLES_QUE_SUBEN,
    DocumentoExpediente,
    ErrorDeExpediente,
)
from obractrl.domain.reportes.expediente import (
    ExpedienteTecnico,
    OrigenDeEvidencia,
)
from obractrl.domain.shared.diccionario import Rol, TipoExpedienteDoc

AHORA = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
OBRA_ID = "11111111-1111-1111-1111-111111111111"


def _subir(
    rol: Rol = Rol.CONTROL_OBRA,
    nombre: str = "Contrato firmado.pdf",
    url: str = "org/obra/expediente/contrato.pdf",
) -> DocumentoExpediente:
    return DocumentoExpediente.subir(
        obra_id=OBRA_ID,
        tipo=TipoExpedienteDoc.CONTRATO,
        nombre=nombre,
        url=url,
        subido_por="usr-control",
        rol=rol,
    )


class TestQuienSube:
    @pytest.mark.parametrize("rol", ROLES_QUE_SUBEN)
    def test_control_de_obra_y_super_intendente_suben(self, rol: Rol) -> None:
        """§11.2: la lectura es de todos, la subida es de (C, SI)."""
        documento = _subir(rol=rol)
        assert documento.obra_id == OBRA_ID
        assert documento.tipo is TipoExpedienteDoc.CONTRATO

    @pytest.mark.parametrize("rol", [Rol.RESIDENTE, Rol.SUPERVISOR])
    def test_ningun_otro_rol_sube(self, rol: Rol) -> None:
        with pytest.raises(ErrorDeExpediente, match="no puede"):
            _subir(rol=rol)

    def test_el_dominio_guarda_la_regla_aunque_el_router_tenga_su_guarda(self) -> None:
        """La misma regla vive en `exigir_rol` (403 legible) y aquí (§6): que
        el borde la repita no la puede volver opcional puertas adentro."""
        with pytest.raises(ErrorDeExpediente, match=r"§11\.2"):
            _subir(rol=Rol.RESIDENTE)


class TestDatosObligatorios:
    @pytest.mark.parametrize("nombre", ["", "   ", "\t\n"])
    def test_el_nombre_no_puede_venir_vacio(self, nombre: str) -> None:
        """`expediente_doc.nombre` es `not null` (§7.9)."""
        with pytest.raises(ErrorDeExpediente, match="nombre"):
            _subir(nombre=nombre)

    @pytest.mark.parametrize("url", ["", "   "])
    def test_la_clave_de_r2_no_puede_venir_vacia(self, url: str) -> None:
        with pytest.raises(ErrorDeExpediente, match="R2"):
            _subir(url=url)

    def test_recorta_los_espacios_de_los_bordes(self) -> None:
        documento = _subir(nombre="  Acta de entrega.pdf  ", url="  org/obra/acta  ")
        assert documento.nombre == "Acta de entrega.pdf"
        assert documento.url == "org/obra/acta"

    def test_la_url_es_la_clave_del_objeto_no_una_firma(self) -> None:
        """§12.2: el binario nunca viaja por la API; lo que persiste es la
        clave, porque la URL firmada caduca."""
        documento = _subir(url="org-1/obra-1/expediente/plano-A3.pdf")
        assert documento.url == "org-1/obra-1/expediente/plano-A3.pdf"
        assert "?" not in documento.url and "X-Amz" not in documento.url


# ---------------------------------------------------------------------------
# El agregado (§11.2 `GET /obras/{id}/expediente/vista`, PDF)
# ---------------------------------------------------------------------------


def _expediente(**cambios: object) -> ExpedienteTecnico:
    argumentos: dict[str, object] = {
        "obra": {
            "id": OBRA_ID,
            "clave": "OBR-001",
            "estatus": "en_proceso",
            "avance_pct": Decimal("42.5"),
        },
        "generado_en": AHORA,
        "documentos": [
            {
                "id": "doc-1",
                "tipo": "contrato",
                "nombre": "Contrato.pdf",
                "url": "org/obra/contrato.pdf",
                "fecha": AHORA,
                "subido_por": "usr-control",
            },
            {
                "id": "doc-2",
                "tipo": "plano",
                "nombre": "Planta baja.pdf",
                "url": "org/obra/planta.pdf",
                "fecha": None,
                "subido_por": None,
            },
            {
                "id": "doc-3",
                "tipo": "plano",
                "nombre": "Planta alta.pdf",
                "url": "org/obra/alta.pdf",
                "fecha": None,
                "subido_por": None,
            },
        ],
        "cierres": [
            {
                "id": "cie-1",
                "actividad_id": "act-1",
                "estatus": "validada",
                "cantidad": Decimal("10"),
                "monto": Decimal("1000.00"),
                "adjuntos": ["org/obra/cierre-1.jpg"],
                "fecha_solicitud": AHORA,
                "fecha_valida": AHORA,
            },
            {
                "id": "cie-2",
                "actividad_id": "act-2",
                "estatus": "solicitada",
                "cantidad": Decimal("5"),
                "monto": Decimal("500.00"),
                "adjuntos": [],
                "fecha_solicitud": AHORA,
            },
            {
                "id": "cie-3",
                "actividad_id": "act-3",
                "estatus": "rechazada",
                "cantidad": Decimal("2"),
                "monto": Decimal("250.00"),
                "adjuntos": None,
            },
        ],
        "estimaciones": [
            {
                "id": "est-1",
                "folio": "EST-2026-33-001",
                "semana": 33,
                "anio": 2026,
                "modo": "destajo",
                "estatus": "validada",
                "monto_total": Decimal("900.00"),
            },
            {
                "id": "est-2",
                "folio": None,
                "semana": 34,
                "anio": 2026,
                "modo": "destajo",
                "estatus": "borrador",
                "monto_total": Decimal("400.00"),
            },
        ],
        "revisiones": [
            {
                "id": "rev-1",
                "fotos": ["org/obra/rev-1a.jpg", "org/obra/rev-1b.jpg"],
                "fecha": date(2026, 8, 17),
            }
        ],
        "incidencias": [
            {
                "id": "inc-1",
                "evidencias": ["org/obra/inc-1.jpg"],
                "fecha_creada": AHORA,
            }
        ],
    }
    argumentos.update(cambios)
    return ExpedienteTecnico.armar(**argumentos)  # type: ignore[arg-type]


class TestSumasDelExpediente:
    def test_solo_suma_los_cierres_validados(self) -> None:
        """§11.3 C.3: una solicitud `solicitada` o `rechazada` todavía no es
        obra reconocida, y el expediente sostiene el cierre de obra (§11.3 D)."""
        assert _expediente().monto_cerrado.monto == Decimal("1000.00")

    def test_solo_suma_las_estimaciones_validadas(self) -> None:
        """§11.3 E.4: un borrador aún puede cambiar de monto."""
        assert _expediente().monto_estimado.monto == Decimal("900.00")

    def test_sin_registros_las_sumas_son_cero_y_no_nulas(self) -> None:
        vacio = _expediente(
            documentos=[], cierres=[], estimaciones=[], revisiones=[], incidencias=[]
        )
        assert vacio.monto_cerrado.es_cero
        assert vacio.monto_estimado.es_cero
        assert vacio.n_evidencias == 0

    def test_un_monto_nulo_en_la_base_no_tumba_el_expediente(self) -> None:
        """`solicitud_cierre.monto` es opcional mientras no hay CPU."""
        expediente = _expediente(
            cierres=[
                {
                    "id": "cie-1",
                    "actividad_id": "act-1",
                    "estatus": "validada",
                    "cantidad": Decimal("10"),
                    "monto": None,
                }
            ]
        )
        assert expediente.monto_cerrado.es_cero


class TestEvidenciasReunidas:
    def test_reune_las_tres_fuentes_del_spec(self) -> None:
        """§7.9 declara una tabla `Evidencia` genérica, pero hoy las claves
        viven dentro de cada entidad (§7.8): el agregado las une sin inventar
        una cuarta fuente."""
        expediente = _expediente()
        assert expediente.n_evidencias == 4
        assert expediente.evidencias_por_origen == {
            OrigenDeEvidencia.REVISION: 2,
            OrigenDeEvidencia.INCIDENCIA: 1,
            OrigenDeEvidencia.CIERRE: 1,
        }

    def test_cada_evidencia_dice_de_donde_viene(self) -> None:
        """Un expediente auditable no puede tener una foto huérfana."""
        for evidencia in _expediente().evidencias:
            assert evidencia.origen_id
            assert evidencia.clave

    def test_la_fecha_de_una_revision_es_date_y_la_de_una_incidencia_datetime(
        self,
    ) -> None:
        """§7.8: `revision_fisica.fecha` es `date`, `incidencia.fecha_creada`
        es `timestamptz`. El agregado no las uniforma; el DTO del borde sí."""
        por_origen = {e.origen: e for e in _expediente().evidencias}
        assert por_origen[OrigenDeEvidencia.REVISION].fecha == date(2026, 8, 17)
        assert por_origen[OrigenDeEvidencia.INCIDENCIA].fecha == AHORA

    @pytest.mark.parametrize(
        "columna", [None, [], "no-es-lista", [None, ""], [123, "  "], {"a": 1}]
    )
    def test_una_columna_jsonb_a_medio_migrar_no_tumba_el_expediente(
        self, columna: object
    ) -> None:
        """`revision_fisica.fotos` es `jsonb` libre: un `null` suelto o un
        objeto de otra forma no puede dejar sin expediente a la obra."""
        expediente = _expediente(
            revisiones=[{"id": "rev-1", "fotos": columna}],
            incidencias=[],
            cierres=[],
        )
        assert expediente.n_evidencias == 0


class TestConteoDeDocumentos:
    def test_cuenta_por_tipo_del_enum_canonico(self) -> None:
        assert _expediente().documentos_por_tipo == {
            TipoExpedienteDoc.CONTRATO: 1,
            TipoExpedienteDoc.PLANO: 2,
        }

    def test_un_tipo_fuera_del_enum_no_pasa_callado(self) -> None:
        """§8.2: el tipo viene del enum canónico. Si la base trajera otro, es
        un defecto de datos y tiene que reventar aquí, no dibujarse en el PDF."""
        with pytest.raises(ValueError, match="inventado"):
            _expediente(
                documentos=[
                    {
                        "id": "doc-1",
                        "tipo": "inventado",
                        "nombre": "X",
                        "url": "org/obra/x",
                    }
                ]
            )


class TestIdentidadDeLaObra:
    def test_conserva_clave_estatus_y_avance(self) -> None:
        expediente = _expediente()
        assert expediente.obra_clave == "OBR-001"
        assert expediente.obra_estatus == "en_proceso"
        assert expediente.avance_pct == Decimal("42.5")

    def test_el_reloj_entra_por_el_borde(self) -> None:
        """§12.11: el dominio no consulta la hora, la recibe — por eso el
        agregado es reproducible en una prueba."""
        assert _expediente().generado_en == AHORA
