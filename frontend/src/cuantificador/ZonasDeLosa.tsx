/**
 * Zonas de losa (Fase 1: geometría y cotas; la matriz de conceptos de cada zona es la fase 2, en `MatrizDeLaZona`).
 *
 * - `PanelDeZonasDeLosa`: las zonas del plano (nombre, nivel, cota del piso, altura libre al nivel bajo de la losa y espesor), con
 *   «Dibujar losa» (el polígono que se trace nace como losa de esa zona) y «Colocar punto de nivel exterior» (cota y rótulo).
 *   Cotas relativas al piso terminado de la planta baja = 0. **Solo Control de obra edita; los demás leen.**
 * - `ZonaDeLosaDelTrazo`: en el detalle del trazo elegido: un polígono (a qué zona pertenece, espesor propio de subzona), un punto
 *   (su cota y su rótulo) o un muro (qué zona, altura, enrase y cara aplicarían, por tramo). Lo del muro es una sugerencia: solo se
 *   aplica al pulsar «Aplicar al muro». Una línea (una trabe, una nervadura) se puede **medir como elemento de la losa** de una zona: su longitud
 *   deriva de la línea y de la escala del plano.
 * - La capa «espacio» (0143): el panel muestra los espacios de la obra y el detalle del trazo asigna un polígono de losa o un muro a su espacio (un muro
 *   también se comparte entre dos); la matriz de cada zona reparte sus elementos por espacio.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { queryClient } from '@/app/queryClient';
import {
  getResolverMuroApiV1TrazosTrazoIdZonasDeLosaGetQueryKey,
  getZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGetQueryKey,
  useAplicarZonaAlMuroApiV1TrazosTrazoIdZonasDeLosaAplicarPost,
  useBorrarZonaApiV1ZonasDeLosaZonaIdDelete,
  useCambiarZonaApiV1ZonasDeLosaZonaIdPut,
  useCrearZonaApiV1PlanosPlanoIdZonasDeLosaPost,
  useFijarLosaApiV1TrazosTrazoIdLosaPut,
  useFijarNivelExteriorApiV1TrazosTrazoIdNivelExteriorPut,
  useResolverMuroApiV1TrazosTrazoIdZonasDeLosaGet,
  useZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGet,
} from '@/api/generado/zonas-de-losa/zonas-de-losa';
import type { ZonaDeLosa } from '@/api/generado/modelo';
import { useAgregarEscaleraApiV1ZonasDeLosaZonaIdEscalerasPost } from '@/api/generado/escaleras/escaleras';
import {
  useAgregarElementoApiV1ZonasDeLosaZonaIdElementosPost,
  useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet,
} from '@/api/generado/losas/losas';
import { EspacioDelTrazo, PanelDeEspacios, useEspaciosDeLaObra } from './EspaciosDeLaObra';
import { MatrizDeLaZona } from './MatrizDeLaZona';
import { EscalerasDeLaZona } from './EscalerasDeLaZona';
import { RellenosDeLaZona } from './RellenosDeLaZona';
import { NOMBRE_DE_CARA, NOMBRE_DE_ORIGEN_DE_ALTURA, NOMBRE_DE_ORIGEN_DE_LADO, textoDeCota, textoDeMetros } from './zonasDeLosa';

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

/** Lo que el plano pide cuando se está colocando algo: una losa de una zona o un punto de nivel. */
export type PorColocar =
  | { readonly tipo: 'losa'; readonly zonaId: string; readonly nombre: string }
  | { readonly tipo: 'nivel'; readonly cotaM: string; readonly rotulo: string };

interface PanelProps {
  readonly planoId: string;
  /** La obra del plano (0143): con ella el panel muestra los espacios y la matriz de cada zona se reparte por espacio. */
  readonly obraId?: string;
  readonly puedeEditar: boolean;
  /** El rol de quien mira: Costos y Control de obra proponen los conceptos nuevos de la matriz. */
  readonly rol?: string | null;
  readonly colocando: PorColocar | null;
  readonly onColocar: (c: PorColocar | null) => void;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

interface Borrador {
  nombre: string;
  nivel: string;
  cota: string;
  altura: string;
  espesor: string;
}
const BORRADOR_VACIO: Borrador = { nombre: '', nivel: '', cota: '0', altura: '3.00', espesor: '0.12' };

function datosDe(b: Borrador) {
  return {
    nombre: b.nombre,
    nivel: b.nivel.trim() || null,
    cota_piso_m: b.cota,
    altura_libre_m: b.altura,
    espesor_m: b.espesor,
  };
}

export function PanelDeZonasDeLosa({ planoId, obraId = '', puedeEditar, rol = null, colocando, onColocar, onCambio, onError }: PanelProps) {
  const consulta = useZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGet(planoId, { query: { enabled: planoId !== '' } });
  const espacios = useEspaciosDeLaObra(obraId);
  const crear = useCrearZonaApiV1PlanosPlanoIdZonasDeLosaPost<ErrorApi>();
  const cambiar = useCambiarZonaApiV1ZonasDeLosaZonaIdPut<ErrorApi>();
  const borrar = useBorrarZonaApiV1ZonasDeLosaZonaIdDelete<ErrorApi>();
  const [editando, setEditando] = useState<string | 'nueva' | null>(null);
  const [borrador, setBorrador] = useState<Borrador>(BORRADOR_VACIO);
  const [cotaNivel, setCotaNivel] = useState('0');
  const [rotuloNivel, setRotuloNivel] = useState('');
  const zonas = consulta.data?.zonas ?? [];
  const puntos = consulta.data?.puntos_de_nivel ?? [];

  function refrescar() {
    void queryClient.invalidateQueries({ queryKey: getZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGetQueryKey(planoId) });
    void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/trazos') });
    void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
    void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('fachada-por-bandas') });
  }

  async function guardar() {
    try {
      if (editando === 'nueva') {
        await crear.mutateAsync({ planoId, data: datosDe(borrador) });
        onCambio(`Zona «${borrador.nombre.trim()}» creada.`);
      } else if (editando) {
        await cambiar.mutateAsync({ zonaId: editando, data: datosDe(borrador) });
        onCambio(`Zona «${borrador.nombre.trim()}» guardada.`);
      }
      setEditando(null);
      refrescar();
    } catch (err) {
      onError(mensaje(err, 'No se pudo guardar la zona.'));
    }
  }

  function empezarAEditar(z: ZonaDeLosa) {
    setBorrador({ nombre: z.nombre, nivel: z.nivel ?? '', cota: z.cota_piso_m, altura: z.altura_libre_m, espesor: z.espesor_m });
    setEditando(z.id);
  }

  async function quitar(z: ZonaDeLosa) {
    try {
      await borrar.mutateAsync({ zonaId: z.id });
      if (colocando?.tipo === 'losa' && colocando.zonaId === z.id) onColocar(null);
      refrescar();
      onCambio(`Zona «${z.nombre}» borrada: sus polígonos quedan como trazos comunes.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo borrar la zona.'));
    }
  }

  const campo = (clave: keyof Borrador, etiqueta: string, ayuda?: string) => (
    <label className="mct__campo" title={ayuda}>
      {etiqueta}
      <input className="input" aria-label={etiqueta} value={borrador[clave]} onChange={(e) => setBorrador({ ...borrador, [clave]: e.target.value })} />
    </label>
  );

  return (
    <>
    {obraId !== '' && <PanelDeEspacios obraId={obraId} puedeEditar={puedeEditar} onCambio={onCambio} onError={onError} />}
    <section className="zonas-losa" aria-label="Zonas de losa" data-testid="zonas-de-losa">
      <div className="estacion__subencabezado">
        <span className="estacion__subtitulo">Zonas de losa</span>
        {puedeEditar && (
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => {
              setBorrador(BORRADOR_VACIO);
              setEditando('nueva');
            }}
          >
            Nueva zona
          </button>
        )}
      </div>
      <p className="text-mute text-xs">
        Cotas en metros, relativas al piso terminado de planta baja = 0. La altura libre va del piso terminado al nivel bajo de la losa
        (es la altura que toma el muro); el espesor es la cota que sigue.
        {!puedeEditar && ' Solo Control de obra las edita.'}
      </p>
      {consulta.data && !consulta.data.escala_definida && (
        <p className="text-mute text-xs">El plano no tiene escala calibrada: se toma 1 unidad de plano = 1 m.</p>
      )}
      {zonas.length === 0 && editando === null && <div className="text-mute text-sm">Este plano no tiene zonas de losa.</div>}
      {zonas.map((z) => (
        <div key={z.id} className="zonas-losa__zona" data-testid="zona-de-losa">
          <div className="row">
            <strong>{z.nombre}</strong>
            {z.nivel && <span className="badge badge--outline">{z.nivel}</span>}
          </div>
          <div className="text-xs mono">
            piso {textoDeCota(z.cota_piso_m)} · libre {textoDeMetros(z.altura_libre_m)} · losa {textoDeCota(z.cota_inferior_m)} a{' '}
            {textoDeCota(z.cota_superior_m)} (e {textoDeMetros(z.espesor_m)})
          </div>
          <div className="text-mute text-xs">
            {z.losas.length} {z.losas.length === 1 ? 'losa' : 'losas'}
            {z.losas.some((l) => l.espesor_propio_m != null) && ` · subzonas: ${z.losas.filter((l) => l.espesor_propio_m != null).length}`}
          </div>
          <MatrizDeLaZona zona={z} puedeEditar={puedeEditar} rol={rol ?? (puedeEditar ? 'control_obra' : null)} espacios={espacios} onCambio={onCambio} onError={onError} />
          <RellenosDeLaZona zona={z} puedeEditar={puedeEditar} rol={rol ?? (puedeEditar ? 'control_obra' : null)} espacios={espacios} onCambio={onCambio} onError={onError} />
          <EscalerasDeLaZona zona={z} zonas={zonas} puedeEditar={puedeEditar} rol={rol ?? (puedeEditar ? 'control_obra' : null)} espacios={espacios} onCambio={onCambio} onError={onError} />
          {puedeEditar && (
            <div className="row">
              <button
                type="button"
                className={colocando?.tipo === 'losa' && colocando.zonaId === z.id ? 'btn btn--sm is-active' : 'btn btn--sm'}
                aria-pressed={colocando?.tipo === 'losa' && colocando.zonaId === z.id}
                onClick={() => onColocar(colocando?.tipo === 'losa' && colocando.zonaId === z.id ? null : { tipo: 'losa', zonaId: z.id, nombre: z.nombre })}
              >
                Dibujar losa
              </button>
              <button type="button" className="btn btn--sm" onClick={() => empezarAEditar(z)}>
                Editar
              </button>
              <button type="button" className="btn btn--sm" aria-label={`Borrar la zona ${z.nombre}`} onClick={() => void quitar(z)}>
                Borrar
              </button>
            </div>
          )}
        </div>
      ))}
      {puedeEditar && editando !== null && (
        <div className="zonas-losa__form" role="group" aria-label="Datos de la zona">
          {campo('nombre', 'Nombre de la zona')}
          {campo('nivel', 'Nivel o planta', 'Texto libre: planta baja, entrepiso…')}
          {campo('cota', 'Cota del piso terminado (m)', 'Piso terminado de PB = 0')}
          {campo('altura', 'Altura libre (m)', 'Del piso terminado al nivel bajo de la losa')}
          {campo('espesor', 'Espesor de la losa (m)')}
          <div className="row">
            <button type="button" className="btn btn--sm btn--primary" disabled={crear.isPending || cambiar.isPending} onClick={() => void guardar()}>
              Guardar zona
            </button>
            <button type="button" className="btn btn--sm" onClick={() => setEditando(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
      <div className="estacion__subencabezado">
        <span className="estacion__subtitulo">Puntos de nivel exterior</span>
      </div>
      {puntos.length === 0 && <div className="text-mute text-sm">Sin puntos de nivel exterior.</div>}
      {puntos.map((p) => (
        <div key={p.trazo_id} className="text-xs mono" data-testid="punto-de-nivel">
          {p.rotulo ?? 'Sin rótulo'} · {textoDeCota(p.cota_m)}
        </div>
      ))}
      {puedeEditar && (
        <div className="zonas-losa__form" role="group" aria-label="Punto de nivel exterior">
          <label className="mct__campo">
            Cota del punto (m)
            <input className="input" aria-label="Cota del punto de nivel" value={cotaNivel} onChange={(e) => setCotaNivel(e.target.value)} />
          </label>
          <label className="mct__campo">
            Rótulo
            <input className="input" aria-label="Rótulo del punto de nivel" value={rotuloNivel} onChange={(e) => setRotuloNivel(e.target.value)} />
          </label>
          <button
            type="button"
            className={colocando?.tipo === 'nivel' ? 'btn btn--sm is-active' : 'btn btn--sm'}
            aria-pressed={colocando?.tipo === 'nivel'}
            onClick={() => onColocar(colocando?.tipo === 'nivel' ? null : { tipo: 'nivel', cotaM: cotaNivel, rotulo: rotuloNivel })}
          >
            Colocar punto de nivel exterior
          </button>
        </div>
      )}
      {colocando && (
        <p className="text-xs" role="status">
          {colocando.tipo === 'losa'
            ? `Traza el área de la losa de «${colocando.nombre}» (polígono o rectángulo). Esc termina.`
            : 'Haz clic en el plano para poner el punto (herramienta Punto). Esc termina.'}
        </p>
      )}
    </section>
    </>
  );
}

interface TrazoProps {
  readonly trazoId: string;
  readonly planoId: string;
  /** La obra del plano (0143): con ella el detalle del trazo ofrece asignarlo a un espacio. */
  readonly obraId?: string;
  readonly tipoDeGeometria: string;
  readonly esMuro: boolean;
  /** El trazo es una línea con grosor, o sea un muro: solo un muro se asigna a un espacio o se comparte entre dos. */
  readonly conGrosor?: boolean;
  readonly losaZonaId: string | null;
  readonly losaEspesorM: string | null;
  readonly nivelExteriorM: string | null;
  readonly rotulo: string | null;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

/** En el detalle del trazo elegido: su rol de losa, su punto de nivel o lo que las zonas dicen de su muro. */
export function ZonaDeLosaDelTrazo(p: TrazoProps) {
  const zonasConsulta = useZonasDelPlanoApiV1PlanosPlanoIdZonasDeLosaGet(p.planoId, { query: { enabled: p.planoId !== '' } });
  const zonas = zonasConsulta.data?.zonas ?? [];
  const hayZonas = zonas.length > 0;
  const obraId = p.obraId ?? '';
  if (p.tipoDeGeometria === 'Polygon') {
    return (
      <>
        <RolDeLosa {...p} zonas={zonas} />
        {p.losaZonaId && obraId !== '' && (
          <EspacioDelTrazo obraId={obraId} trazoId={p.trazoId} esMuro={false} puedeEditar={p.puedeEditar} onCambio={p.onCambio} onError={p.onError} />
        )}
      </>
    );
  }
  if (p.tipoDeGeometria === 'Point') return <PuntoDeNivel {...p} />;
  if (p.tipoDeGeometria === 'LineString' && p.conGrosor && obraId !== '' && !hayZonas) {
    return <EspacioDelTrazo obraId={obraId} trazoId={p.trazoId} esMuro puedeEditar={p.puedeEditar} onCambio={p.onCambio} onError={p.onError} />;
  }
  if (p.tipoDeGeometria === 'LineString' && hayZonas) {
    return (
      <>
        {p.esMuro && <ZonaDelMuro {...p} />}
        {p.conGrosor && obraId !== '' && (
          <EspacioDelTrazo obraId={obraId} trazoId={p.trazoId} esMuro puedeEditar={p.puedeEditar} onCambio={p.onCambio} onError={p.onError} />
        )}
        {p.puedeEditar && <ElementoDeLosaDeLaLinea {...p} zonas={zonas} />}
        {p.puedeEditar && <EscaleraDeLaLinea {...p} zonas={zonas} />}
      </>
    );
  }
  return null;
}

function refrescarTodo() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/trazos') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/muro') });
}

function RolDeLosa(p: TrazoProps & { readonly zonas: readonly ZonaDeLosa[] }) {
  const fijar = useFijarLosaApiV1TrazosTrazoIdLosaPut<ErrorApi>();
  const [espesor, setEspesor] = useState(p.losaEspesorM ?? '');
  const zona = p.zonas.find((z) => z.id === p.losaZonaId);
  if (p.zonas.length === 0 && !p.losaZonaId) return null;
  async function poner(zonaId: string | null, espesorM: string | null) {
    try {
      await fijar.mutateAsync({ trazoId: p.trazoId, data: { zona_id: zonaId, espesor_m: espesorM } });
      refrescarTodo();
      p.onCambio(zonaId ? 'Polígono marcado como losa de su zona.' : 'El polígono ya no es una losa.');
    } catch (err) {
      p.onError(mensaje(err, 'No se pudo marcar la losa.'));
    }
  }
  return (
    <div className="zonas-losa__trazo" data-testid="losa-del-trazo">
      <div className="opciones__titulo">Losa de zona</div>
      <label className="mct__campo">
        Zona
        <select className="input" aria-label="Zona de la losa" value={p.losaZonaId ?? ''} disabled={!p.puedeEditar || fijar.isPending} onChange={(e) => void poner(e.target.value || null, null)}>
          <option value="">No es una losa</option>
          {p.zonas.map((z) => (
            <option key={z.id} value={z.id}>
              {z.nombre} · libre {z.altura_libre_m} m
            </option>
          ))}
        </select>
      </label>
      {zona && (
        <>
          <label className="mct__campo" title="Subzona: espesor estructural propio dentro de la zona">
            Espesor propio de esta losa (m)
            <input className="input" aria-label="Espesor propio de la losa" placeholder={`el de la zona: ${zona.espesor_m}`} value={espesor} disabled={!p.puedeEditar} onChange={(e) => setEspesor(e.target.value)} />
          </label>
          {p.puedeEditar && (
            <button type="button" className="btn btn--sm" onClick={() => void poner(zona.id, espesor.trim() || null)}>
              Guardar espesor
            </button>
          )}
          <p className="text-mute text-xs">
            Espesor que aplica: {textoDeMetros(p.losaEspesorM ?? zona.espesor_m)}
            {p.losaEspesorM ? ' (subzona, por razón estructural)' : ' (el de la zona)'}.
          </p>
        </>
      )}
    </div>
  );
}

function PuntoDeNivel(p: TrazoProps) {
  const fijar = useFijarNivelExteriorApiV1TrazosTrazoIdNivelExteriorPut<ErrorApi>();
  const [cota, setCota] = useState(p.nivelExteriorM ?? '0');
  const [rotulo, setRotulo] = useState(p.rotulo ?? '');
  async function guardar(quitar: boolean) {
    try {
      await fijar.mutateAsync({ trazoId: p.trazoId, data: { cota_m: quitar ? null : cota, rotulo: quitar ? null : rotulo.trim() || null } });
      refrescarTodo();
      p.onCambio(quitar ? 'Punto de nivel exterior quitado.' : 'Punto de nivel exterior guardado.');
    } catch (err) {
      p.onError(mensaje(err, 'No se pudo guardar el punto de nivel.'));
    }
  }
  if (p.nivelExteriorM == null && !p.puedeEditar) return null;
  return (
    <div className="zonas-losa__trazo" data-testid="nivel-del-trazo">
      <div className="opciones__titulo">Punto de nivel exterior</div>
      <label className="mct__campo">
        Cota (m)
        <input className="input" aria-label="Cota del punto de nivel exterior" value={cota} disabled={!p.puedeEditar} onChange={(e) => setCota(e.target.value)} />
      </label>
      <label className="mct__campo">
        Rótulo
        <input className="input" aria-label="Rótulo del punto de nivel exterior" value={rotulo} disabled={!p.puedeEditar} onChange={(e) => setRotulo(e.target.value)} />
      </label>
      {p.puedeEditar && (
        <div className="row">
          <button type="button" className="btn btn--sm" onClick={() => void guardar(false)}>
            {p.nivelExteriorM == null ? 'Marcar como punto de nivel exterior' : 'Guardar punto de nivel'}
          </button>
          {p.nivelExteriorM != null && (
            <button type="button" className="btn btn--sm" onClick={() => void guardar(true)}>
              Quitar la marca
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ZonaDelMuro(p: TrazoProps) {
  const consulta = useResolverMuroApiV1TrazosTrazoIdZonasDeLosaGet(p.trazoId);
  const aplicarAlMuro = useAplicarZonaAlMuroApiV1TrazosTrazoIdZonasDeLosaAplicarPost<ErrorApi>();
  const r = consulta.data;
  if (!r || !r.con_zona) return null;
  const unico = r.tramos.length === 1 ? r.tramos[0] : undefined;
  // Un muro que trae su altura la conserva (manda sobre la de la zona): no hay nada que aplicar.
  const aplicable = r.altura_explicita_m == null;
  async function aplicar() {
    if (!r) return;
    try {
      const res = await aplicarAlMuro.mutateAsync({ trazoId: p.trazoId });
      void queryClient.invalidateQueries({ queryKey: getResolverMuroApiV1TrazosTrazoIdZonasDeLosaGetQueryKey(p.trazoId) });
      refrescarTodo();
      const conEnrase = (unico?.partes.length ?? 0) > 1;
      p.onCambio(
        unico
          ? `Altura de la zona aplicada al muro: ${textoDeMetros(unico.altura_m)}${conEnrase ? ' con enrase y altura por cara' : ''}.`
          : `Altura de la zona aplicada al muro: cuenta por ${res.tramos.length} tramos dentro del mismo trazo (${res.enlaces_aplicados} enlace${res.enlaces_aplicados === 1 ? '' : 's'}).`,
      );
    } catch (err) {
      p.onError(mensaje(err, 'No se pudo aplicar la zona al muro.'));
    }
  }
  return (
    <div className="zonas-losa__trazo" data-testid="zona-del-muro">
      <div className="opciones__titulo">Zona de losa de este muro</div>
      <p className="text-mute text-xs">Lo que sigue es lo que la losa sugiere; no cambia el muro hasta que lo apliques.</p>
      {r.parte_el_muro && (
        <span className="badge badge--warn" data-testid="muro-por-partir">
          Cruza zonas de distinta altura: cuenta por {r.tramos.length} tramos dentro del mismo trazo (no se parte; los vanos van al tramo donde caen).
        </span>
      )}
      <table className="table" aria-label="Tramos del muro por zona de losa">
        <thead>
          <tr>
            <th>Tramo</th>
            <th>Altura</th>
            <th>Cara A</th>
            <th>Cara B</th>
          </tr>
        </thead>
        <tbody>
          {r.tramos.map((t, i) => (
            <tr key={i} data-testid="tramo-de-zona">
              <td className="mono">
                {textoDeMetros(t.desde_m)}–{textoDeMetros(t.hasta_m)}
              </td>
              <td>
                {textoDeMetros(t.altura_m)}
                <div className="text-mute text-xs">{NOMBRE_DE_ORIGEN_DE_ALTURA[t.origen_de_altura]}</div>
                {t.enrase && (
                  <div className="text-xs" data-testid="enrase-del-tramo">
                    enrase {textoDeMetros(t.enrase.desde_m)}–{textoDeMetros(t.enrase.hasta_m)}
                  </div>
                )}
                {t.partes.length > 1 && (
                  <ul className="text-xs" aria-label="Altura por cara" data-testid="partes-por-cara">
                    {t.partes.map((x) => (
                      <li key={x.nombre} data-testid="parte-por-cara">
                        {x.nombre} {textoDeMetros(x.desde_m)}–{textoDeMetros(x.hasta_m)} · A {NOMBRE_DE_CARA[x.cara_a ?? ''] ?? 'sin zona'} · B {NOMBRE_DE_CARA[x.cara_b ?? ''] ?? 'sin zona'}
                      </li>
                    ))}
                  </ul>
                )}
                {(r.vanos_por_tramo[i] ?? []).length > 0 && (
                  <div className="text-mute text-xs" data-testid="vanos-del-tramo">
                    Vanos: {(r.vanos_por_tramo[i] ?? []).map((v) => v.clave).join(', ')}
                  </div>
                )}
              </td>
              {[t.lado_a, t.lado_b].map((l) => (
                <td key={l.lado}>
                  <strong>{l.cara ?? 'sin zona'}</strong>
                  <div className="text-mute text-xs">
                    {l.zona ?? NOMBRE_DE_ORIGEN_DE_LADO[l.origen]}
                    {l.altura_m != null && ` · ${textoDeMetros(l.altura_m)}`}
                    {l.rotulo_del_punto && ` · ${l.rotulo_del_punto} ${textoDeCota(l.nivel_exterior_m ?? 0)}`}
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {r.altura_guardada_m != null && Number(r.altura_guardada_m) !== Number(unico?.altura_m ?? r.altura_guardada_m) && (
        <p className="text-mute text-xs">Hoy mide con {textoDeMetros(r.altura_guardada_m)}; lo guardado no cambia solo.</p>
      )}
      {r.advertencias.map((a) => (
        <p key={a} className="text-mute text-xs">
          {a}
        </p>
      ))}
      {aplicable && r.tramos.some((t) => t.origen_de_altura === 'zona') && (
        <button type="button" className="btn btn--sm" disabled={aplicarAlMuro.isPending} onClick={() => void aplicar()}>
          Aplicar al muro
        </button>
      )}
    </div>
  );
}

/** En el detalle de una línea: medirla como un elemento (trabe, contratrabe, nervadura) de la losa de una zona; su longitud deriva de la línea. */
function ElementoDeLosaDeLaLinea(p: TrazoProps & { readonly zonas: readonly ZonaDeLosa[] }) {
  const ficha = useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet('LOSA-MACIZA');
  const agregar = useAgregarElementoApiV1ZonasDeLosaZonaIdElementosPost<ErrorApi>();
  const [zonaId, setZonaId] = useState('');
  const [clave, setClave] = useState('');
  const [modo, setModo] = useState<'ml' | 'pieza'>('ml');
  const [pago, setPago] = useState<'en_la_losa' | 'propio'>('en_la_losa');
  const permitidos = ficha.data?.elementos_permitidos ?? [];
  const zona = p.zonas.find((z) => z.id === zonaId) ?? p.zonas[0];
  const elemento = clave || permitidos[0]?.clave || '';
  if (!zona) return null;
  async function medir() {
    if (!zona || elemento === '') return;
    try {
      await agregar.mutateAsync({ zonaId: zona.id, data: { elemento_clave: elemento, modo, pago, trazo_id: p.trazoId } });
      refrescarTodo();
      p.onCambio(`${elemento} medido con esta línea en la matriz de «${zona.nombre}».`);
    } catch (err) {
      p.onError(mensaje(err, 'No se pudo medir el elemento con la línea.'));
    }
  }
  return (
    <div className="zonas-losa__trazo" data-testid="elemento-de-losa-de-la-linea">
      <div className="opciones__titulo">Medir un elemento de losa</div>
      <p className="text-mute text-xs">La longitud de esta línea (con la escala del plano) es la medida del elemento: si la línea cambia, la matriz cambia.</p>
      <label className="mct__campo">
        Zona
        <select className="input" aria-label="Zona del elemento de losa" value={zona.id} onChange={(e) => setZonaId(e.target.value)}>
          {p.zonas.map((z) => (
            <option key={z.id} value={z.id}>
              {z.nombre}
            </option>
          ))}
        </select>
      </label>
      <label className="mct__campo">
        Elemento
        <select className="input" aria-label="Elemento de losa de la línea" value={elemento} onChange={(e) => setClave(e.target.value)}>
          {permitidos.map((x) => (
            <option key={x.clave} value={x.clave}>
              {x.clave}
            </option>
          ))}
        </select>
      </label>
      <label className="mct__campo">
        Se mide por
        <select className="input" aria-label="Se mide por la línea" value={modo} onChange={(e) => setModo(e.target.value as 'ml' | 'pieza')}>
          <option value="ml">ml de la línea</option>
          <option value="pieza">una pieza del largo de la línea</option>
        </select>
      </label>
      <label className="mct__campo">
        Pago
        <select className="input" aria-label="Pago del elemento de la línea" value={pago} onChange={(e) => setPago(e.target.value as 'en_la_losa' | 'propio')}>
          <option value="en_la_losa">paga la losa</option>
          <option value="propio">paga su concepto por ml</option>
        </select>
      </label>
      <button type="button" className="btn btn--sm" disabled={agregar.isPending} onClick={() => void medir()}>
        Medir con esta línea
      </button>
    </div>
  );
}

/** En el detalle de una línea: tomarla como el recorrido horizontal de una escalera que arranca en una zona; de su longitud (con la escala) sale la huella. */
function EscaleraDeLaLinea(p: TrazoProps & { readonly zonas: readonly ZonaDeLosa[] }) {
  const agregar = useAgregarEscaleraApiV1ZonasDeLosaZonaIdEscalerasPost<ErrorApi>();
  const [zonaId, setZonaId] = useState('');
  const zona = p.zonas.find((z) => z.id === zonaId) ?? p.zonas[0];
  if (!zona) return null;
  async function medir() {
    if (!zona) return;
    try {
      await agregar.mutateAsync({ zonaId: zona.id, data: { trazo_id: p.trazoId } });
      refrescarTodo();
      p.onCambio(`Escalera agregada a «${zona.nombre}» con el recorrido de esta línea.`);
    } catch (err) {
      p.onError(mensaje(err, 'No se pudo tomar la línea como recorrido de una escalera.'));
    }
  }
  return (
    <div className="zonas-losa__trazo" data-testid="escalera-de-la-linea">
      <div className="opciones__titulo">Usar como recorrido de una escalera</div>
      <p className="text-mute text-xs">
        La longitud de esta línea (con la escala del plano) es el recorrido horizontal de las rampas y de ella sale la huella: si la línea cambia, la escalera cambia. Una línea no sirve a dos escaleras.
      </p>
      <label className="mct__campo">
        Arranca en
        <select className="input" aria-label="Zona de arranque de la escalera de la línea" value={zona.id} onChange={(e) => setZonaId(e.target.value)}>
          {p.zonas.map((z) => (
            <option key={z.id} value={z.id}>
              {z.nombre}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="btn btn--sm" disabled={agregar.isPending} onClick={() => void medir()}>
        Medir una escalera con esta línea
      </button>
    </div>
  );
}
