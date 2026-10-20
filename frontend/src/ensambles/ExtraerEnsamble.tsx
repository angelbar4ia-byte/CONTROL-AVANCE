/**
 * Extracción: arma un ensamble desde lo ya construido — `POST /ensambles`
 * (§11.2, solo Control de obra; skill `erp-parametrico` §6).
 *
 * Esta pantalla **no camina el presupuesto ni adivina nada**: quien captura
 * decide, renglón por renglón, qué concepto o sub-ensamble entra, con qué
 * cantidad y con qué origen (§2: heredada del concepto, heredada de un
 * destajo, manual). Es la misma regla que se fijó para `modo_cantidad`: el
 * sistema propone, el usuario decide, y nada queda escrito hasta confirmar.
 *
 * Las cantidades son **receta, no volumen** (§2): cuánto entra por una
 * instancia completa de la plantilla, no cuánto salió en una obra concreta.
 *
 * La cohorte se **declara a mano** (§5.7): ningún prototipo entra por una
 * regla calculada, porque la condición que de verdad separa a los prototipos
 * no se adivina, se descubre con datos y se declara.
 */

import { useState, type FormEvent } from 'react';

import { useListarPrototiposApiV1PrototiposGet } from '@/api/generado/proyectos/proyectos';
import { useExtraerEnsambleApiV1EnsamblesPost } from '@/api/generado/ensambles/ensambles';
import type { EnsambleCreadoRespuesta, PrototipoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from '@/catalogos/Campos';
import {
  OPCIONES_ORIGEN,
  RENGLON_VACIO,
  peticionRenglon,
  renglonCompleto,
  type FormularioRenglon,
} from './reglas';

interface Props {
  readonly onCerrar: () => void;
  readonly onCreado: (creado: EnsambleCreadoRespuesta) => void;
}

export function ExtraerEnsamble({ onCerrar, onCreado }: Props) {
  const [clave, setClave] = useState('');
  const [nombre, setNombre] = useState('');
  const [divisorClave, setDivisorClave] = useState('');
  const [divisorNombre, setDivisorNombre] = useState('');
  const [renglones, setRenglones] = useState<readonly FormularioRenglon[]>([RENGLON_VACIO]);
  const [cohorte, setCohorte] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const prototiposQ = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>();

  const crear = useExtraerEnsambleApiV1EnsamblesPost<ErrorApi>({
    mutation: {
      onSuccess: (creado) => {
        setError(null);
        onCreado(creado);
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const completo =
    clave.trim() !== '' &&
    nombre.trim() !== '' &&
    renglones.length > 0 &&
    renglones.every(renglonCompleto) &&
    // El divisor se declara completo o no se declara: la tasa lo necesita
    // junto con su nombre (§5.7).
    (divisorClave.trim() === '') === (divisorNombre.trim() === '');
  const puedeEnviar = completo && !crear.isPending;

  function cambiarRenglon(indice: number, cambios: Partial<FormularioRenglon>) {
    setRenglones((actuales) => actuales.map((r, i) => (i === indice ? { ...r, ...cambios } : r)));
  }

  function alternarPrototipo(id: string) {
    setCohorte((actual) => {
      const siguiente = new Set(actual);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  }

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({
      data: {
        clave: clave.trim(),
        nombre: nombre.trim(),
        renglones: renglones.map((r, i) => peticionRenglon(r, i + 1)),
        divisor_concepto_clave: divisorClave.trim() === '' ? null : divisorClave.trim(),
        divisor_nombre: divisorNombre.trim() === '' ? null : divisorNombre.trim(),
        cohorte_prototipo_ids: [...cohorte],
      },
    });
  }

  return (
    <Modal titulo="Nuevo ensamble (Extracción)" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        {/* Scroll y flex-columna en dos niveles: como hijos directos de un
            `.col` con altura acotada, las `.card` (overflow: hidden) se
            comprimen y recortan sus campos en vez de dejar que haga scroll. */}
        <div className="sheet__body" style={{ maxHeight: '70vh' }}>
         <div className="col gap-12">
          <div className="row gap-12" style={{ alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="ens-clave"
                etiqueta="Clave"
                valor={clave}
                onCambio={setClave}
                mono
                requerido
                pista="Identidad del ensamble (§3.3); no se puede repetir."
              />
            </div>
            <div style={{ flex: 2 }}>
              <CampoTexto
                id="ens-nombre"
                etiqueta="Nombre"
                valor={nombre}
                onCambio={setNombre}
                requerido
                marcador="Recámara tipo A"
              />
            </div>
          </div>

          {/* ── Renglones ─────────────────────────────────────────── */}
          <section className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Renglones de la receta</h3>
                <div className="card__sub">
                  Cada renglón es un concepto o un sub-ensamble, nunca los dos. La cantidad es lo
                  que entra por una instancia completa (§2).
                </div>
              </div>
            </div>
            <div className="card__body col gap-12">
              {renglones.map((renglon, i) => (
                <div key={i} className="row gap-8" style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div style={{ flex: '0 0 150px' }}>
                    <CampoSelect
                      id={`ens-r${i}-tipo`}
                      etiqueta="Es un"
                      valor={renglon.tipo}
                      onCambio={(tipo) =>
                        cambiarRenglon(i, { tipo: tipo === 'sub_ensamble' ? 'sub_ensamble' : 'concepto' })
                      }
                      opciones={[
                        { valor: 'concepto', etiqueta: 'Concepto' },
                        { valor: 'sub_ensamble', etiqueta: 'Sub-ensamble' },
                      ]}
                    />
                  </div>
                  <div style={{ flex: '1 1 160px' }}>
                    <CampoTexto
                      id={`ens-r${i}-clave`}
                      etiqueta="Clave"
                      valor={renglon.clave}
                      onCambio={(valor) => cambiarRenglon(i, { clave: valor })}
                      mono
                    />
                  </div>
                  <div style={{ flex: '0 0 110px' }}>
                    <CampoTexto
                      id={`ens-r${i}-cantidad`}
                      etiqueta="Cantidad"
                      valor={renglon.cantidad}
                      onCambio={(valor) => cambiarRenglon(i, { cantidad: valor })}
                      tipo="number"
                      mono
                      paso="any"
                      minimo="0"
                    />
                  </div>
                  <div style={{ flex: '1 1 190px' }}>
                    <CampoSelect
                      id={`ens-r${i}-origen`}
                      etiqueta="Origen de la cantidad"
                      valor={renglon.origen}
                      onCambio={(origen) => cambiarRenglon(i, { origen })}
                      opciones={OPCIONES_ORIGEN}
                    />
                  </div>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    aria-label={`Quitar renglón ${i + 1}`}
                    disabled={renglones.length === 1}
                    onClick={() => setRenglones((actuales) => actuales.filter((_, j) => j !== i))}
                  >
                    Quitar
                  </button>
                </div>
              ))}
              <div className="row">
                <button
                  type="button"
                  className="btn"
                  onClick={() => setRenglones((actuales) => [...actuales, RENGLON_VACIO])}
                >
                  Agregar renglón
                </button>
              </div>
            </div>
          </section>

          {/* ── Divisor (opcional) ───────────────────────────────── */}
          <section className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Divisor de la tasa (opcional)</h3>
                <div className="card__sub">
                  El concepto contra el que se normaliza el costo de este ensamble (§5.7): para
                  cimentación es el desplante, no el m² total. Se declara con su nombre, o no se
                  declara.
                </div>
              </div>
            </div>
            <div className="card__body row gap-12">
              <div style={{ flex: 1 }}>
                <CampoTexto
                  id="ens-divisor-clave"
                  etiqueta="Clave del concepto divisor"
                  valor={divisorClave}
                  onCambio={setDivisorClave}
                  mono
                />
              </div>
              <div style={{ flex: 1 }}>
                <CampoTexto
                  id="ens-divisor-nombre"
                  etiqueta="Nombre del divisor"
                  valor={divisorNombre}
                  onCambio={setDivisorNombre}
                  marcador="m² de desplante"
                />
              </div>
            </div>
          </section>

          {/* ── Cohorte (declarada a mano) ───────────────────────── */}
          <section className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Cohorte de referencia (opcional)</h3>
                <div className="card__sub">
                  Los prototipos sobre los que se mide la tasa. Se declaran a mano: nunca una regla
                  calculada (§5.7).
                </div>
              </div>
              <span className="badge badge--outline tnum">{cohorte.size} elegidos</span>
            </div>
            <div className="card__body col gap-4">
              {prototiposQ.isLoading && <div className="text-mute text-sm">Cargando prototipos…</div>}
              {prototiposQ.isError && <ErrorBanner mensaje={prototiposQ.error.message} />}
              {(prototiposQ.data ?? []).map((prototipo) => (
                <label key={prototipo.id} className="row gap-8 text-sm">
                  <input
                    type="checkbox"
                    checked={cohorte.has(prototipo.id)}
                    onChange={() => alternarPrototipo(prototipo.id)}
                  />
                  <span className="mono">{prototipo.clave}</span>
                  <span className="text-mute">{prototipo.nombre}</span>
                </label>
              ))}
            </div>
          </section>

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
         </div>
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear ensamble'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
