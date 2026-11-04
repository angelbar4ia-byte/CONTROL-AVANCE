/**
 * Tablas de los catálogos de Catálogos · APU (§7.3, §10.1, §11.2 bloque
 * "Catálogos · APU") y del árbol de prototipo (§7.4): unidades, familias,
 * insumos/materiales, conceptos, contratistas, cuadrillas, niveles y etapas
 * de construcción, y prototipos.
 *
 * Presentación pura: reciben lo que el servidor ya devolvió —acotado por RLS
 * a su organización (§12.4)— y ya filtrado/ordenado por `busqueda.ts` según
 * la prioridad de CLAVE (§3.3). No calculan nada.
 *
 * La **clave es la primera columna** en todas, con `is-key` y en mono: es
 * el identificador con el que se cruza todo el sistema (§3.3), no un dato
 * más. Cuando un registro entró solo porque su descripción coincidió, se
 * marca — así se ve que la clave no fue la que casó.
 */

import type { ReactNode } from 'react';

import {
  FilasVirtuales,
  useTablaVirtual,
  type ControlTablaVirtual,
} from '@/lib/tablaVirtual';

import type {
  ContratistaRespuesta,
  ConceptoRespuesta,
  CuadrillaRespuesta,
  EtapaRespuesta,
  FamiliaRespuesta,
  InsumoRespuesta,
  NivelRespuesta,
  PrototipoRespuesta,
  ProyectoRespuesta,
  EspecialidadRespuesta,
  UnidadRespuesta,
} from '@/api/generado/modelo';
import { fmtMXN, fmtNum, fmtPct } from '@/lib/formato';
import { CeldasNivelesYRecamaras } from '@/proyectos/NivelesYRecamaras';
import type { Resultado } from './busqueda';
import { soloPorDescripcion } from './busqueda';
import {
  etiquetaEstatusCatalogo,
  etiquetaTipoConcepto,
  etiquetaTipoInsumo,
  ivaDelInsumo,
  notaOrigenIva,
  tonoEstatusCatalogo,
} from './reglas';

/**
 * Envoltura común: encabezados, cargando y vacío, para no repetirlo seis veces.
 *
 * `virtual` es opcional a propósito. El §12.9 nombra el **catálogo de
 * conceptos/CPU** como vista de miles de renglones, y los insumos crecen con él
 * —un catálogo real trae ambos por millares—. Unidades, familias y contratistas
 * son decenas: virtualizarlas costaría un viewport acotado y un `Ctrl+F` que
 * deja de encontrar, a cambio de nada.
 */
function TablaCatalogo({
  columnas,
  vacia,
  cargando,
  filas,
  virtual,
  children,
}: {
  readonly columnas: readonly string[];
  readonly vacia: string;
  readonly cargando: boolean;
  readonly filas: number;
  readonly virtual?: ControlTablaVirtual<unknown>;
  readonly children: ReactNode;
}) {
  return (
    <div className="table-wrap">
      <div className="table-scroll" ref={virtual?.ref} style={virtual?.estilo}>
        <table className="table">
          <thead>
            <tr>
              {columnas.map((columna) => (
                <th key={columna}>{columna}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cargando ? (
              <Aviso columnas={columnas.length}>Cargando…</Aviso>
            ) : filas === 0 ? (
              <Aviso columnas={columnas.length}>{vacia}</Aviso>
            ) : (
              children
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Aviso({ columnas, children }: { readonly columnas: number; readonly children: ReactNode }) {
  return (
    <tr>
      <td colSpan={columnas}>
        <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
          {children}
        </div>
      </td>
    </tr>
  );
}

/** Celda de clave: mono, y con la marca de "casó por descripción" (§3.3). */
function Clave({ valor, porDescripcion }: { readonly valor: string; readonly porDescripcion: boolean }) {
  return (
    <td className="is-key">
      {valor}
      {porDescripcion && (
        <>
          {' '}
          <span
            className="badge badge--outline"
            title="La clave no coincide con la búsqueda; casó la descripción (§3.3)."
          >
            desc
          </span>
        </>
      )}
    </td>
  );
}

function Estatus({ estatus }: { readonly estatus: string }) {
  return (
    <td>
      <span className={`badge badge--${tonoEstatusCatalogo(estatus)}`}>
        {etiquetaEstatusCatalogo(estatus)}
      </span>
    </td>
  );
}

const COLUMNAS_UNIDADES = ['Clave', 'Nombre', 'Sinónimos', 'Factor', 'Estatus'] as const;

export function TablaUnidades({
  resultados,
  cargando,
}: {
  readonly resultados: readonly Resultado<UnidadRespuesta>[];
  readonly cargando: boolean;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_UNIDADES}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay unidades con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => (
        <tr key={item.id}>
          <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
          <td>{item.nombre}</td>
          <td className="text-mute mono text-xs">
            {item.sinonimos && item.sinonimos.length > 0 ? item.sinonimos.join(' · ') : '—'}
          </td>
          <td className="is-num">{fmtNum(item.factor)}</td>
          <Estatus estatus={item.estatus ?? 'activo'} />
        </tr>
      ))}
    </TablaCatalogo>
  );
}

const COLUMNAS_FAMILIAS = ['Clave', 'Nombre', 'Aplica a', 'Padre', 'IVA', 'Estatus'] as const;

export function TablaFamilias({
  resultados,
  familias,
  cargando,
}: {
  readonly resultados: readonly Resultado<FamiliaRespuesta>[];
  /** Todas las familias, para resolver el nombre del padre del árbol (§7.3). */
  readonly familias: readonly FamiliaRespuesta[];
  readonly cargando: boolean;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_FAMILIAS}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay familias con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => {
        const padre = familias.find((familia) => familia.id === item.parent_id);
        return (
          <tr key={item.id}>
            <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
            <td>{item.nombre}</td>
            <td className="text-mute text-sm">{item.aplica_a ?? '—'}</td>
            <td className="text-mute mono text-xs">{padre ? padre.clave : '—'}</td>
            <td>
              {item.iva_aplica === null || item.iva_aplica === undefined ? (
                <span className="text-mute text-sm">—</span>
              ) : (
                <span className={`badge badge--${item.iva_aplica ? 'info' : 'outline'}`}>
                  {item.iva_aplica ? 'Grava' : 'Exenta'}
                </span>
              )}
            </td>
            <Estatus estatus={item.estatus ?? 'activo'} />
          </tr>
        );
      })}
    </TablaCatalogo>
  );
}

const COLUMNAS_INSUMOS = [
  'Clave',
  'Descripción',
  'Tipo',
  'Unidad',
  'Cuadrilla',
  'Rend. teórico',
  'Familia',
  'Costo base',
  'Costo vigente',
  'IVA',
  'Estatus',
] as const;

export function TablaInsumos({
  resultados,
  unidades,
  familias,
  cuadrillas,
  cargando,
  vacia,
}: {
  readonly resultados: readonly Resultado<InsumoRespuesta>[];
  readonly unidades: readonly UnidadRespuesta[];
  readonly familias: readonly FamiliaRespuesta[];
  /** Para resolver `cuadrilla_id` (§10.6, solo `tipo=mano_obra`/`subcontrato`). */
  readonly cuadrillas: readonly CuadrillaRespuesta[];
  readonly cargando: boolean;
  readonly vacia: string;
}) {
  const virtual = useTablaVirtual(resultados);
  return (
    <TablaCatalogo
      columnas={COLUMNAS_INSUMOS}
      cargando={cargando}
      filas={resultados.length}
      vacia={vacia}
      virtual={virtual as ControlTablaVirtual<unknown>}
    >
      <FilasVirtuales control={virtual}>
      {({ item, coincidencia }) => {
        const familia = familias.find((f) => f.id === item.familia_id);
        const iva = ivaDelInsumo(item, familia);
        return (
          <tr key={item.id}>
            <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
            <td>{item.descripcion}</td>
            <td className="text-mute text-sm">{etiquetaTipoInsumo(item.tipo)}</td>
            <td className="mono text-xs">
              {unidades.find((u) => u.id === item.unidad_id)?.clave ?? '—'}
            </td>
            <td className="mono text-xs">
              {cuadrillas.find((c) => c.id === item.cuadrilla_id)?.clave ?? '—'}
            </td>
            <td className="is-num">{fmtNum(item.rendimiento_teorico)}</td>
            <td className="mono text-xs">{familia?.clave ?? '—'}</td>
            <td className="is-num">{fmtMXN(item.costo_base)}</td>
            {/* `costo_base_actualizado` = costo último más reciente = costo
                vigente (§10.1, §10.5). Lo mantiene el cargador de almacén. */}
            <td className="is-num">{fmtMXN(item.costo_base_actualizado)}</td>
            {/* Se muestra el valor que el backend guardó y de dónde salió
                (§3.5: la familia siembra, el insumo puede sobrescribir).
                Aquí no se calcula impuesto alguno. */}
            <td title={notaOrigenIva(iva.origen)}>
              {iva.aplica === null ? (
                <span className="text-mute text-sm">—</span>
              ) : (
                <span className={`badge badge--${iva.aplica ? 'info' : 'outline'}`}>
                  {iva.aplica ? 'Grava' : 'Exento'}
                </span>
              )}
              {iva.origen === 'insumo' && (
                <>
                  {' '}
                  <span className="badge badge--warn">override</span>
                </>
              )}
            </td>
            <Estatus estatus={item.estatus ?? 'activo'} />
          </tr>
        );
      }}
      </FilasVirtuales>
    </TablaCatalogo>
  );
}

const COLUMNAS_CONCEPTOS = [
  'Clave',
  'Descripción',
  'Tipo',
  'Unidad',
  'Familia',
  // El oficio con el que se ejecuta (§8.3, migración 0047). Editable en la
  // tabla y no en un diálogo aparte porque lo que hace falta es rellenar
  // decenas seguidas: el catálogo cargado clasifica 461 de 898 conceptos y el
  // resto sale como «Sin oficio» al desglosar un frente.
  'Oficio',
  'Estatus',
  'APU',
] as const;

export function TablaConceptos({
  resultados,
  unidades,
  familias,
  especialidades,
  cargando,
  conceptoAbierto,
  onAbrirAPU,
  onCambiarOficio,
}: {
  readonly resultados: readonly Resultado<ConceptoRespuesta>[];
  readonly unidades: readonly UnidadRespuesta[];
  readonly familias: readonly FamiliaRespuesta[];
  readonly especialidades?: readonly EspecialidadRespuesta[];
  readonly cargando: boolean;
  readonly conceptoAbierto: string | null;
  /** Ausente cuando el rol no consulta el APU (§11.2: CPU/explosión = C, SI). */
  readonly onAbrirAPU?: (concepto: ConceptoRespuesta) => void;
  /** Ausente cuando el rol no configura catálogos: la celda queda de lectura. */
  readonly onCambiarOficio?: (conceptoId: string, especialidadId: string | null) => void;
}) {
  const virtual = useTablaVirtual(resultados);
  return (
    <TablaCatalogo
      columnas={COLUMNAS_CONCEPTOS}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay conceptos con estos filtros."
      virtual={virtual as ControlTablaVirtual<unknown>}
    >
      <FilasVirtuales control={virtual}>
      {({ item, coincidencia }) => (
        <tr
          key={item.id}
          style={item.id === conceptoAbierto ? { background: 'var(--c-elev)' } : undefined}
        >
          <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
          <td>{item.descripcion}</td>
          <td className="text-mute text-sm">{etiquetaTipoConcepto(item.tipo)}</td>
          <td className="mono text-xs">
            {unidades.find((u) => u.id === item.unidad_id)?.clave ?? '—'}
          </td>
          <td className="mono text-xs">
            {familias.find((f) => f.id === item.familia_id)?.clave ?? '—'}
          </td>
          <CeldaOficio
            concepto={item}
            especialidades={especialidades ?? []}
            onCambiar={onCambiarOficio}
          />
          <Estatus estatus={item.estatus ?? 'activo'} />
          <td className="cell-actions">
            {onAbrirAPU && (
              <button
                type="button"
                className="btn btn--sm"
                aria-haspopup="dialog"
                onClick={() => onAbrirAPU(item)}
              >
                Ver APU
              </button>
            )}
          </td>
        </tr>
      )}
      </FilasVirtuales>
    </TablaCatalogo>
  );
}

const COLUMNAS_CONTRATISTAS = [
  'Clave',
  'Razón social',
  'RFC',
  'Contacto',
  'Teléfono',
  'Calificación',
  'Estatus',
] as const;

export function TablaContratistas({
  resultados,
  cargando,
}: {
  readonly resultados: readonly Resultado<ContratistaRespuesta>[];
  readonly cargando: boolean;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_CONTRATISTAS}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay contratistas con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => (
        <tr key={item.id}>
          <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
          <td>{item.razon_social}</td>
          <td className="mono text-xs">{item.rfc ?? '—'}</td>
          <td>{item.contacto ?? '—'}</td>
          <td className="mono text-xs">{item.telefono ?? '—'}</td>
          <td className="is-num">{fmtNum(item.calificacion)}</td>
          <Estatus estatus={item.estatus ?? 'activo'} />
        </tr>
      ))}
    </TablaCatalogo>
  );
}

const COLUMNAS_CUADRILLAS = [
  'Clave',
  'Nombre',
  'Unidad',
  'Rendimiento',
  // Lo que cuesta un día de la cuadrilla (§7.6, migración 0048). Editable
  // aquí porque es la mitad que falta del precio que el residente arma para un
  // trabajo fuera de catálogo: sin esto sale reportado como "no se sabe".
  'Costo jornada',
  'PU vigente',
  'Versión',
  'Estatus',
] as const;

export function TablaCuadrillas({
  resultados,
  unidades,
  cargando,
  onCambiarCosto,
}: {
  readonly resultados: readonly Resultado<CuadrillaRespuesta>[];
  /** Para resolver la unidad a la que refiere el PU (§10.6). */
  readonly unidades: readonly UnidadRespuesta[];
  readonly cargando: boolean;
  /** Ausente cuando el rol no configura catálogos: la celda queda de lectura. */
  readonly onCambiarCosto?: (cuadrillaId: string, costo: number | null) => void;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_CUADRILLAS}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay cuadrillas con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => {
        const unidad = unidades.find((u) => u.id === item.unidad_id);
        return (
          <tr key={item.id}>
            <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
            <td>{item.nombre}</td>
            <td className="text-mute mono text-xs">{unidad ? unidad.clave : '—'}</td>
            {/* Rendimiento teórico asignado por el cargador de mano de obra
                (§10.6) — no el que trae la propia fila cabecera de cuadrillas. */}
            <td className="is-num">{fmtNum(item.rendimiento)}</td>
            {onCambiarCosto ? (
              <td className="is-num">
                <input
                  className="input is-num"
                  type="number"
                  min={0}
                  step="any"
                  style={{ maxWidth: 110 }}
                  defaultValue={item.costo_jornada ?? ''}
                  placeholder="—"
                  aria-label={`Costo por jornada de ${item.clave}`}
                  onBlur={(e) => {
                    const texto = e.target.value.trim();
                    // Vacío quita el costo. No es lo mismo que cero: cero diría
                    // que la cuadrilla es gratis y el precio armado lo sumaría
                    // como tal; vacío dice que no se ha capturado y se reporta.
                    const valor = texto === '' ? null : Number(texto);
                    if (String(item.costo_jornada ?? '') === texto) return;
                    onCambiarCosto(item.id, valor);
                  }}
                />
              </td>
            ) : (
              <td className="is-num">
                {item.costo_jornada === null || item.costo_jornada === undefined
                  ? '—'
                  : fmtMXN(item.costo_jornada)}
              </td>
            )}
            <td className="is-num">
              {item.precio_unitario === null || item.precio_unitario === undefined
                ? '—'
                : fmtMXN(item.precio_unitario)}
            </td>
            <td className="text-mute text-sm">{item.version_vigente ?? '—'}</td>
            <Estatus estatus={item.estatus ?? 'activo'} />
          </tr>
        );
      })}
    </TablaCatalogo>
  );
}

const COLUMNAS_NIVELES = ['Clave', 'Descripción', 'Orden', 'Importe'] as const;

export function TablaNiveles({
  resultados,
  cargando,
}: {
  readonly resultados: readonly Resultado<NivelRespuesta>[];
  readonly cargando: boolean;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_NIVELES}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay niveles de construcción con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => (
        <tr key={item.id}>
          <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
          <td>{item.descripcion}</td>
          <td className="is-num tnum">{item.orden}</td>
          <td className="is-num">
            {item.importe === null || item.importe === undefined ? '—' : fmtMXN(item.importe)}
          </td>
        </tr>
      ))}
    </TablaCatalogo>
  );
}

const COLUMNAS_ETAPAS = ['Clave', 'Descripción', 'Nivel', 'Orden', 'Ponderación', 'Importe'] as const;

export function TablaEtapas({
  resultados,
  niveles,
  cargando,
  onCambiarNivel,
}: {
  readonly resultados: readonly Resultado<EtapaRespuesta>[];
  /** Para resolver la clave del nivel al que pertenece la etapa (§7.4). */
  readonly niveles: readonly NivelRespuesta[];
  readonly cargando: boolean;
  /** Ausente cuando el rol no configura catálogos: la celda queda de lectura. */
  readonly onCambiarNivel?: (etapaId: string, nivelId: string | null) => void;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_ETAPAS}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay etapas de construcción con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => (
        <tr key={item.id}>
          <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
          <td>{item.descripcion}</td>
          {onCambiarNivel && niveles.length > 0 ? (
            <td>
              <select
                className="select"
                value={item.nivel_id ?? ''}
                aria-label={`Nivel de ${item.clave}`}
                onChange={(e) => onCambiarNivel(item.id, e.target.value || null)}
              >
                <option value="">Sin nivel</option>
                {niveles.map((nivel) => (
                  <option key={nivel.id} value={nivel.id}>
                    {nivel.clave} · {nivel.descripcion}
                  </option>
                ))}
              </select>
            </td>
          ) : (
            <td className="mono text-xs">
              {niveles.find((nivel) => nivel.id === item.nivel_id)?.clave ?? '—'}
            </td>
          )}
          <td className="is-num tnum">{item.orden}</td>
          <td className="is-num">{fmtPct(item.ponderacion)}</td>
          <td className="is-num">
            {item.importe === null || item.importe === undefined ? '—' : fmtMXN(item.importe)}
          </td>
        </tr>
      ))}
    </TablaCatalogo>
  );
}

const COLUMNAS_PROTOTIPOS = ['Clave', 'Nombre', 'Proyecto', 'm²', 'Niveles', 'Recámaras'] as const;

export function TablaPrototipos({
  resultados,
  proyectos,
  cargando,
  puedeEditar = false,
}: {
  /** Control de obra y Super intendente llenan niveles y recámaras aquí. */
  readonly puedeEditar?: boolean;
  readonly resultados: readonly Resultado<PrototipoRespuesta>[];
  /** Para resolver la clave/nombre del proyecto al que pertenece (§7.2). */
  readonly proyectos: readonly ProyectoRespuesta[];
  readonly cargando: boolean;
}) {
  return (
    <TablaCatalogo
      columnas={COLUMNAS_PROTOTIPOS}
      cargando={cargando}
      filas={resultados.length}
      vacia="No hay prototipos con estos filtros."
    >
      {resultados.map(({ item, coincidencia }) => {
        const proyecto = proyectos.find((p) => p.id === item.proyecto_id);
        return (
          <tr key={item.id}>
            <Clave valor={item.clave} porDescripcion={soloPorDescripcion(coincidencia)} />
            <td>{item.nombre}</td>
            <td className="text-mute text-sm">
              {proyecto ? `${proyecto.clave} · ${proyecto.nombre}` : '—'}
            </td>
            <td className="is-num tnum">{fmtNum(item.m2)}</td>
            <CeldasNivelesYRecamaras prototipo={item} editable={puedeEditar} />
          </tr>
        );
      })}
    </TablaCatalogo>
  );
}

/**
 * El oficio de un concepto, editable en la celda.
 *
 * Un `<select>` y no un diálogo porque el trabajo real es rellenar decenas
 * seguidas: el catálogo cargado clasifica 461 de 898 conceptos, y abrir y
 * cerrar un modal por cada uno haría que nadie lo terminara.
 *
 * Guarda al elegir, sin botón de confirmar. Es un solo campo de una lista
 * cerrada: no hay estado a medias que confirmar, y el valor anterior se
 * recupera volviendo a elegirlo.
 */
function CeldaOficio({
  concepto,
  especialidades,
  onCambiar,
}: {
  readonly concepto: ConceptoRespuesta;
  readonly especialidades: readonly EspecialidadRespuesta[];
  readonly onCambiar?: (conceptoId: string, especialidadId: string | null) => void;
}) {
  const actual = especialidades.find((e) => e.id === concepto.especialidad_id);

  if (!onCambiar || especialidades.length === 0) {
    return (
      <td className="mono text-xs">
        {actual?.clave ?? <span className="text-mute">—</span>}
      </td>
    );
  }

  return (
    <td>
      <select
        className="select"
        value={concepto.especialidad_id ?? ''}
        aria-label={`Oficio de ${concepto.clave}`}
        onChange={(e) => onCambiar(concepto.id, e.target.value || null)}
      >
        <option value="">Sin oficio</option>
        {especialidades.map((especialidad) => (
          <option key={especialidad.id} value={especialidad.id}>
            {especialidad.clave} · {especialidad.nombre}
          </option>
        ))}
      </select>
    </td>
  );
}
