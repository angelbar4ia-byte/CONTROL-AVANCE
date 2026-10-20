/**
 * Lo que pasó al generar o regenerar una instancia (skill `erp-parametrico`
 * §6, §8 regla 11: "nunca arrasar ni respetar en silencio").
 *
 * Solo dos clases se escribieron solas —`nuevo` y `actualizado`—. Las otras
 * tres (`desvinculado`, `conflicto`, `sobra`) **no se tocaron**: la pantalla
 * las pone arriba y con las tres cifras a la vista —lo que tiene la partida
 * hoy, lo que tenía al generarse y lo que el ensamble pide ahora— porque la
 * decisión es de quien lee, no del sistema. Nada sale del presupuesto sin que
 * el usuario lo decida.
 *
 * Se pinta como una tarjeta por renglón, no como una tabla: vive en un modal
 * de 480px y una tabla de cinco columnas dejaba fuera de la vista justo las
 * dos cifras que se comparan.
 *
 * Todo viene calculado del backend: aquí no se compara ni se recalcula nada.
 */

import type { RenglonGeneradoRespuesta, ReporteGeneracionRespuesta } from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { etiquetaEstadoRenglon, explicacionEstado, tonoEstadoRenglon } from './reglas';

interface Props {
  readonly reporte: ReporteGeneracionRespuesta;
}

export function ReporteGeneracion({ reporte }: Props) {
  const pendientes = reporte.pendientes;

  return (
    <div className="col gap-12" data-testid="reporte-generacion">
      <div className="row gap-8">
        <Conteo etiqueta="Nuevos" valor={reporte.nuevos.length} nota="Creados sin preguntar" />
        <Conteo
          etiqueta="Actualizados"
          valor={reporte.actualizados.length}
          nota="Nadie los había tocado"
        />
        <Conteo etiqueta="Por decidir" valor={pendientes.length} nota="No se tocaron" />
      </div>

      {pendientes.length === 0 ? (
        <div className="text-mute text-sm" role="status">
          No hay nada por decidir: todo lo que pedía el ensamble se escribió o se refrescó.
        </div>
      ) : (
        <section className="col gap-8" aria-label="Renglones por decidir">
          <div className="text-sm">
            <strong>Nada de esto se escribió solo.</strong> Revisa cada renglón y decide qué hacer
            con la partida en el presupuesto.
          </div>
          {pendientes.map((renglon) => (
            <TarjetaPendiente key={renglon.clave_concepto} renglon={renglon} />
          ))}
        </section>
      )}

      {(reporte.nuevos.length > 0 || reporte.actualizados.length > 0) && (
        <div className="text-mute text-sm">
          {reporte.nuevos.length > 0 && (
            <div>
              <strong>Nuevos:</strong> <span className="mono">{reporte.nuevos.join(', ')}</span>
            </div>
          )}
          {reporte.actualizados.length > 0 && (
            <div>
              <strong>Actualizados:</strong>{' '}
              <span className="mono">{reporte.actualizados.join(', ')}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Conteo({
  etiqueta,
  valor,
  nota,
}: {
  readonly etiqueta: string;
  readonly valor: number;
  readonly nota: string;
}) {
  return (
    <div className="kpi" style={{ flex: 1, alignSelf: 'stretch' }}>
      <div className="kpi__label">{etiqueta}</div>
      <div className="kpi__value tnum">{valor}</div>
      <div className="kpi__sub">{nota}</div>
    </div>
  );
}

function TarjetaPendiente({ renglon }: { readonly renglon: RenglonGeneradoRespuesta }) {
  const existente = renglon.existente;
  // Una partida capturada a mano nunca se generó: no tiene "lo que tenía al
  // generarse", y fingir una cifra ahí sería inventar historial.
  const capturada = existente != null && existente.snapshot == null;

  return (
    <div className="card" data-estado={renglon.estado}>
      <div className="card__header">
        <span className="mono is-key">{renglon.clave_concepto}</span>
        <span className={`badge badge--${tonoEstadoRenglon(renglon.estado)}`}>
          {etiquetaEstadoRenglon(renglon.estado)}
        </span>
      </div>
      <div className="card__body col gap-8">
        <div
          style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}
        >
          <Cifra
            etiqueta="Tiene hoy"
            cantidad={existente?.actual.cantidad}
            precio={existente?.actual.precio_unitario}
          />
          <Cifra
            etiqueta="Tenía al generarse"
            cantidad={existente?.snapshot?.cantidad}
            precio={existente?.snapshot?.precio_unitario}
            ausente={capturada ? 'Capturada a mano: nunca se generó' : undefined}
          />
          <Cifra
            etiqueta="El ensamble pide hoy"
            cantidad={renglon.receta?.cantidad}
            precio={renglon.receta?.precio_unitario}
          />
        </div>
        <div className="text-mute text-xs">{explicacionEstado(renglon.estado)}</div>
      </div>
    </div>
  );
}

function Cifra({
  etiqueta,
  cantidad,
  precio,
  ausente,
}: {
  readonly etiqueta: string;
  readonly cantidad: string | null | undefined;
  readonly precio: string | null | undefined;
  readonly ausente?: string;
}) {
  const hay = cantidad != null && precio != null;
  return (
    <div>
      <div className="text-mute text-xs" style={{ textTransform: 'uppercase' }}>
        {etiqueta}
      </div>
      {hay ? (
        <div className="tnum text-sm">
          {fmtNum(cantidad)}
          <div className="text-mute text-xs">× {fmtMXN(precio)}</div>
        </div>
      ) : ausente !== undefined ? (
        <div className="text-mute text-xs">{ausente}</div>
      ) : (
        <div className="text-mute text-sm">—</div>
      )}
    </div>
  );
}
