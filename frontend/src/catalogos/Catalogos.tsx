/**
 * Catálogos · APU — pantalla de catálogos maestros y editor de precios
 * unitarios (§7.3, §10.1, §11.2 bloque "Catálogos · APU").
 *
 * Montada en `/config/catalogos`, la entrada "Catálogos" del sidebar de
 * Control de obra (§5.1). El contrato deja todo este bloque en (C) —salvo
 * la lectura del APU, que es (C, SI)—, y el sidebar del Super intendente no
 * trae la entrada, así que no se monta una segunda ruta para él: se montan
 * las rutas que algún sidebar apunta, no las que el contrato permitiría.
 *
 * Seis catálogos en pestañas: unidades, familias, insumos, materiales,
 * conceptos y contratistas. El buscador es **por clave** (§3.3): la clave
 * manda y la descripción solo desempata — `busqueda.ts` lo implementa y esta
 * pantalla solo lo consume.
 *
 * ## Ruta de datos (§10.7)
 *
 * El §10.7 abre la puerta a leer catálogos **directo de Supabase** con
 * supabase-js + RLS. Aquí no se usa, por la misma razón que en `proyectos`:
 * el contrato ya expone `GET /unidades`, `/familias`, `/insumos`,
 * `/materiales`, `/conceptos` y `/contratistas`, y ninguna feature de la app
 * abre hoy la ruta directa. Mantener una sola frontera —API + RLS detrás—
 * evita que el mismo dato llegue por dos caminos con dos comportamientos de
 * caché, y deja el diccionario canónico (§8) del lado del backend, que es
 * quien lo aplica. La escritura, en cualquier caso, va **siempre** por la
 * API (§10.7), y el APU también: es lógica de dominio, no catálogo plano.
 *
 * El cliente de la ruta directa sigue disponible en `lib/supabase.ts` con su
 * lista blanca; si un día se quiere realtime en un select, ese es el lugar.
 */

import { useMemo, useState } from 'react';

import {
  useListarConceptosApiV1ConceptosGet,
  useListarContratistasApiV1ContratistasGet,
  useListarFamiliasApiV1FamiliasGet,
  useListarInsumosApiV1InsumosGet,
  useListarMaterialesApiV1MaterialesGet,
  useListarUnidadesApiV1UnidadesGet,
} from '@/api/generado/catalogos/catalogos';
import { TipoConcepto, TipoInsumo } from '@/api/generado/modelo';
import type {
  ConceptoRespuesta,
  ContratistaRespuesta,
  FamiliaRespuesta,
  InsumoRespuesta,
  UnidadRespuesta,
} from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { buscarPorClave } from './busqueda';
import { AltaConcepto } from './AltaConcepto';
import { AltaContratista } from './AltaContratista';
import { AltaFamilia } from './AltaFamilia';
import { AltaInsumo } from './AltaInsumo';
import { AltaUnidad } from './AltaUnidad';
import { PanelAPU } from './PanelAPU';
import {
  TablaConceptos,
  TablaContratistas,
  TablaFamilias,
  TablaInsumos,
  TablaUnidades,
} from './Tablas';
import {
  etiquetaTipoConcepto,
  etiquetaTipoInsumo,
  puedeAdministrarCatalogos,
  puedeConsultarAPU,
} from './reglas';

type Pestania = 'unidades' | 'familias' | 'insumos' | 'materiales' | 'conceptos' | 'contratistas';

const PESTANIAS: readonly { readonly clave: Pestania; readonly etiqueta: string }[] = [
  { clave: 'conceptos', etiqueta: 'Conceptos' },
  { clave: 'materiales', etiqueta: 'Materiales' },
  { clave: 'insumos', etiqueta: 'Insumos' },
  { clave: 'familias', etiqueta: 'Familias' },
  { clave: 'unidades', etiqueta: 'Unidades' },
  { clave: 'contratistas', etiqueta: 'Contratistas' },
];

const TIPOS_INSUMO: readonly TipoInsumo[] = [
  TipoInsumo.material,
  TipoInsumo.mano_obra,
  TipoInsumo.equipo,
  TipoInsumo.herramienta,
];

const TIPOS_CONCEPTO: readonly TipoConcepto[] = [
  TipoConcepto.concepto,
  TipoConcepto.auxiliar,
  TipoConcepto.matriz,
  TipoConcepto.basico,
];

type Dialogo = Pestania | null;

export default function Catalogos() {
  const { sesion } = useSesion();
  const rol = sesion?.rol ?? null;
  const administra = rol !== null && puedeAdministrarCatalogos(rol);
  const consultaAPU = rol !== null && puedeConsultarAPU(rol);

  const [pestania, setPestania] = useState<Pestania>('conceptos');
  const [texto, setTexto] = useState('');
  const [familiaId, setFamiliaId] = useState('');
  const [tipoInsumo, setTipoInsumo] = useState<TipoInsumo | ''>('');
  const [tipoConcepto, setTipoConcepto] = useState<TipoConcepto | ''>('');
  const [incluirInactivos, setIncluirInactivos] = useState(false);
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [conceptoAbierto, setConceptoAbierto] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  // Unidades y familias se piden siempre: además de su pestaña, resuelven
  // las claves que las demás tablas muestran y alimentan los selects de las
  // altas. Son listas cortas (§8.7, semilla editable).
  const unidadesQ = useListarUnidadesApiV1UnidadesGet<UnidadRespuesta[], ErrorApi>({
    incluir_inactivos: incluirInactivos,
  });

  const familiasQ = useListarFamiliasApiV1FamiliasGet<FamiliaRespuesta[], ErrorApi>({
    incluir_inactivos: incluirInactivos,
  });

  const insumosQ = useListarInsumosApiV1InsumosGet<InsumoRespuesta[], ErrorApi>(
    {
      tipo: tipoInsumo === '' ? undefined : tipoInsumo,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'insumos' } },
  );

  const materialesQ = useListarMaterialesApiV1MaterialesGet<InsumoRespuesta[], ErrorApi>(
    {
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'materiales' } },
  );

  const conceptosQ = useListarConceptosApiV1ConceptosGet<ConceptoRespuesta[], ErrorApi>(
    {
      tipo: tipoConcepto === '' ? undefined : tipoConcepto,
      familia_id: familiaId === '' ? undefined : familiaId,
      incluir_inactivos: incluirInactivos,
    },
    { query: { enabled: pestania === 'conceptos' } },
  );

  const contratistasQ = useListarContratistasApiV1ContratistasGet<
    ContratistaRespuesta[],
    ErrorApi
  >({ incluir_inactivos: incluirInactivos }, { query: { enabled: pestania === 'contratistas' } });

  const unidades = useMemo(() => unidadesQ.data ?? [], [unidadesQ.data]);
  const familias = useMemo(() => familiasQ.data ?? [], [familiasQ.data]);
  const conceptos = useMemo(() => conceptosQ.data ?? [], [conceptosQ.data]);

  const resUnidades = useMemo(
    () => buscarPorClave(unidades, texto, (unidad) => unidad.nombre),
    [unidades, texto],
  );
  const resFamilias = useMemo(
    () => buscarPorClave(familias, texto, (familia) => familia.nombre),
    [familias, texto],
  );
  const resInsumos = useMemo(
    () => buscarPorClave(insumosQ.data ?? [], texto, (insumo) => insumo.descripcion),
    [insumosQ.data, texto],
  );
  const resMateriales = useMemo(
    () => buscarPorClave(materialesQ.data ?? [], texto, (material) => material.descripcion),
    [materialesQ.data, texto],
  );
  const resConceptos = useMemo(
    () => buscarPorClave(conceptos, texto, (concepto) => concepto.descripcion),
    [conceptos, texto],
  );
  const resContratistas = useMemo(
    () =>
      buscarPorClave(contratistasQ.data ?? [], texto, (contratista) => contratista.razon_social),
    [contratistasQ.data, texto],
  );

  // El concepto del cajón se re-deriva de la lista para que un cambio de
  // filtro no deje abierto un APU que ya no está en pantalla.
  const concepto = conceptos.find((c) => c.id === conceptoAbierto) ?? null;

  if (!sesion || rol === null) return null;

  const errores = [
    unidadesQ.error,
    familiasQ.error,
    insumosQ.error,
    materialesQ.error,
    conceptosQ.error,
    contratistasQ.error,
  ].filter((error): error is ErrorApi => error !== null && error !== undefined);

  function cambiarPestania(nueva: Pestania) {
    setPestania(nueva);
    setConceptoAbierto(null);
    // Los filtros de tipo son de una sola pestaña; arrastrarlos entre
    // catálogos dejaría la tabla vacía sin razón visible.
    setTipoInsumo('');
    setTipoConcepto('');
  }

  function tituloAlta(): string {
    switch (pestania) {
      case 'unidades':
        return 'Nueva unidad';
      case 'familias':
        return 'Nueva familia';
      case 'insumos':
        return 'Nuevo insumo';
      case 'materiales':
        return 'Nuevo material';
      case 'conceptos':
        return 'Nuevo concepto';
      case 'contratistas':
        return 'Nuevo contratista';
    }
  }

  function alCrear(mensaje: string) {
    setDialogo(null);
    setAviso(mensaje);
    void unidadesQ.refetch();
    void familiasQ.refetch();
    if (pestania === 'insumos') void insumosQ.refetch();
    if (pestania === 'materiales') void materialesQ.refetch();
    if (pestania === 'conceptos') void conceptosQ.refetch();
    if (pestania === 'contratistas') void contratistasQ.refetch();
  }

  const familiasDelLado = familias.filter((familia) =>
    pestania === 'conceptos'
      ? (familia.aplica_a ?? 'material') === 'concepto'
      : (familia.aplica_a ?? 'material') === 'material',
  );

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Configuración</div>
          <h1 className="page__title">Catálogos · APU</h1>
          <div className="page__subtitle">
            Catálogos maestros y análisis de precios unitarios. La clave es única y manda en
            todo cruce; la descripción solo desempata (§3.3).
          </div>
        </div>

        {administra && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setDialogo(pestania)}
            >
              {tituloAlta()}
            </button>
          </div>
        )}
      </div>

      {aviso !== null && (
        <div className="mb-8" role="status">
          <span className="badge badge--ok">{aviso}</span>
        </div>
      )}

      {errores.map((error, indice) => (
        <div className="mb-8" key={`${error.status}-${indice}`}>
          <ErrorBanner mensaje={error.message} />
        </div>
      ))}

      <div className="tabs mb-8" role="tablist" aria-label="Catálogos">
        {PESTANIAS.map((opcion) => (
          <button
            key={opcion.clave}
            type="button"
            role="tab"
            id={`tab-${opcion.clave}`}
            aria-selected={pestania === opcion.clave}
            // Solo el panel activo existe en el DOM; apuntar al de una
            // pestaña inactiva sería un `aria-controls` colgado.
            aria-controls={pestania === opcion.clave ? `panel-${opcion.clave}` : undefined}
            className={`tabs__tab${pestania === opcion.clave ? ' is-active' : ''}`}
            onClick={() => cambiarPestania(opcion.clave)}
          >
            {opcion.etiqueta}
          </button>
        ))}
      </div>

      <div className="filterbar">
        <input
          className="input search"
          type="search"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Buscar por clave…"
          aria-label="Buscar por clave; la descripción solo desempata (§3.3)"
        />

        {pestania === 'insumos' && (
          <select
            className="select"
            value={tipoInsumo}
            onChange={(e) => setTipoInsumo(e.target.value as TipoInsumo | '')}
            aria-label="Filtrar por tipo de insumo"
          >
            <option value="">Todos los tipos</option>
            {TIPOS_INSUMO.map((tipo) => (
              <option key={tipo} value={tipo}>
                {etiquetaTipoInsumo(tipo)}
              </option>
            ))}
          </select>
        )}

        {pestania === 'conceptos' && (
          <select
            className="select"
            value={tipoConcepto}
            onChange={(e) => setTipoConcepto(e.target.value as TipoConcepto | '')}
            aria-label="Filtrar por tipo de concepto"
          >
            <option value="">Todos los tipos</option>
            {TIPOS_CONCEPTO.map((tipo) => (
              <option key={tipo} value={tipo}>
                {etiquetaTipoConcepto(tipo)}
              </option>
            ))}
          </select>
        )}

        {(pestania === 'insumos' || pestania === 'materiales' || pestania === 'conceptos') && (
          <select
            className="select"
            value={familiaId}
            onChange={(e) => setFamiliaId(e.target.value)}
            aria-label="Filtrar por familia"
          >
            <option value="">Todas las familias</option>
            {familiasDelLado.map((familia) => (
              <option key={familia.id} value={familia.id}>
                {familia.clave} · {familia.nombre}
              </option>
            ))}
          </select>
        )}

        <label className="row gap-4" style={{ alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={incluirInactivos}
            onChange={(e) => setIncluirInactivos(e.target.checked)}
          />
          <span className="text-sm text-mute">Incluir dados de baja</span>
        </label>
      </div>

      {/* `tabIndex={0}`: hay catálogos cuya tabla no tiene ningún control
          enfocable (unidades, familias), y sin esto el panel quedaría
          inalcanzable con teclado tras la pestaña. */}
      <div
        id={`panel-${pestania}`}
        role="tabpanel"
        aria-labelledby={`tab-${pestania}`}
        tabIndex={0}
      >
        {pestania === 'unidades' && (
          <TablaUnidades resultados={resUnidades} cargando={unidadesQ.isLoading} />
        )}

        {pestania === 'familias' && (
          <TablaFamilias
            resultados={resFamilias}
            familias={familias}
            cargando={familiasQ.isLoading}
          />
        )}

        {pestania === 'insumos' && (
          <TablaInsumos
            resultados={resInsumos}
            unidades={unidades}
            familias={familias}
            cargando={insumosQ.isLoading}
            vacia="No hay insumos con estos filtros."
          />
        )}

        {pestania === 'materiales' && (
          <TablaInsumos
            resultados={resMateriales}
            unidades={unidades}
            familias={familias}
            cargando={materialesQ.isLoading}
            vacia="No hay materiales con estos filtros."
          />
        )}

        {pestania === 'conceptos' && (
          <TablaConceptos
            resultados={resConceptos}
            unidades={unidades}
            familias={familias}
            cargando={conceptosQ.isLoading}
            conceptoAbierto={conceptoAbierto}
            onAbrirAPU={consultaAPU ? (elegido) => setConceptoAbierto(elegido.id) : undefined}
          />
        )}

        {pestania === 'contratistas' && (
          <TablaContratistas resultados={resContratistas} cargando={contratistasQ.isLoading} />
        )}
      </div>

      {concepto && (
        <PanelAPU
          key={concepto.id}
          concepto={concepto}
          rol={rol}
          unidad={unidades.find((unidad) => unidad.id === concepto.unidad_id)}
          onCerrar={() => setConceptoAbierto(null)}
        />
      )}

      {dialogo === 'unidades' && (
        <AltaUnidad
          onCerrar={() => setDialogo(null)}
          onCreada={() => alCrear('Unidad creada')}
        />
      )}

      {dialogo === 'familias' && (
        <AltaFamilia
          familias={familias}
          onCerrar={() => setDialogo(null)}
          onCreada={() => alCrear('Familia creada')}
        />
      )}

      {(dialogo === 'insumos' || dialogo === 'materiales') && (
        <AltaInsumo
          unidades={unidades}
          familias={familias}
          soloMaterial={dialogo === 'materiales'}
          onCerrar={() => setDialogo(null)}
          onCreado={() =>
            alCrear(dialogo === 'materiales' ? 'Material creado' : 'Insumo creado')
          }
        />
      )}

      {dialogo === 'conceptos' && (
        <AltaConcepto
          unidades={unidades}
          familias={familias}
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Concepto creado')}
        />
      )}

      {dialogo === 'contratistas' && (
        <AltaContratista
          onCerrar={() => setDialogo(null)}
          onCreado={() => alCrear('Contratista creado')}
        />
      )}
    </div>
  );
}
