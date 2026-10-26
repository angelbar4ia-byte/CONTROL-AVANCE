/**
 * La URL del módulo del cuantificador con su contexto.
 *
 * «Abrir en el módulo» (D-532) lleva *el mismo plano, el mismo concepto y lo ya
 * trazado*. Lo trazado no viaja: ya está en el servidor, que es lo que las dos
 * entradas comparten. Lo único que hace falta pasar es el dónde: la obra, el
 * plano y la actividad.
 */

export interface DestinoDeModulo {
  readonly obraId: string;
  readonly planoId?: string;
  readonly actividadId?: string;
}

export function rutaDelModulo({ obraId, planoId, actividadId }: DestinoDeModulo): string {
  const busqueda = new URLSearchParams({ obra: obraId });
  if (planoId) busqueda.set('plano', planoId);
  if (actividadId) busqueda.set('actividad', actividadId);
  return `/cuantificador?${busqueda.toString()}`;
}
