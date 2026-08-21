/**
 * Avisos en vivo: escucha SSE y recarga lo que cambió (§11.2).
 *
 * El backend publica hechos del dominio en `GET /api/v1/events`
 * (`adapters/api/v1/eventos.py`). Aquí se escuchan y se traducen a
 * invalidaciones de TanStack Query: lo que estaba en pantalla se vuelve a
 * pedir, con el token y el alcance de quien mira.
 *
 * ## Por qué `fetch` y no `EventSource`
 *
 * `EventSource` es la API nativa y sería menos código, pero **no deja poner
 * cabeceras**: el único lugar para el JWT sería la query string, donde acaba
 * en los logs de acceso de Render, en el historial del navegador y en
 * cualquier proxy del camino (§12.4). Con `fetch` + streams el token viaja en
 * `Authorization`, como en todas las demás llamadas.
 *
 * Lo que se pierde es la reconexión automática del navegador, y por eso está
 * escrita abajo con espera creciente.
 *
 * ## Por qué invalidar y no aplicar el aviso
 *
 * El aviso trae ids, nunca contenido —esa es una decisión del servidor, no un
 * ahorro de bytes—. Escribir el cambio en la caché a partir del aviso sería
 * inventar el estado en el cliente, y el cliente **no puede saber** qué le
 * permite ver RLS: un residente conectado no debe pintar una obra ajena
 * porque llegó un aviso de ella. Invalidando, el dato lo vuelve a traer la
 * API con las mismas reglas de siempre.
 *
 * ## Y por qué no invalidar todo
 *
 * `invalidateQueries()` sin filtro recargaría cada consulta activa en cada
 * aviso. En una obra con movimiento eso es un puñado de peticiones por minuto
 * que nadie pidió, y el plan chico de Render las paga (§12.8). El mapa de
 * abajo dice qué toca cada hecho.
 */

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { supabase } from '@/lib/supabase';

const BASE = import.meta.env.VITE_API_URL ?? '';
const RUTA = '/api/v1/events';

/**
 * Espera antes de reintentar, en ms. Crece hasta el último valor y ahí se
 * queda: si la API está caída, insistir cada segundo no la levanta y sí gasta
 * batería en una laptop con la Torre abierta.
 */
const ESPERAS = [1_000, 3_000, 10_000, 30_000];

/**
 * Qué recarga cada hecho, por prefijo de la clave de consulta.
 *
 * Las claves que genera Orval empiezan por la ruta (`['/api/v1/torre', …]`),
 * así que un prefijo de texto alcanza para acertarle a todas sus variantes de
 * parámetros sin enumerarlas.
 */
const AFECTA: Readonly<Record<string, readonly string[]>> = {
  actividad_cerrada: ['/api/v1/torre', '/api/v1/cierres', '/actividades', '/ruta-critica'],
  incidencia_detiene: [
    '/api/v1/torre',
    '/api/v1/incidencias',
    '/actividades',
    '/ruta-critica',
  ],
  estimacion_validada: ['/api/v1/torre', '/estimaciones'],
  cierre_de_obra_completado: ['/api/v1/torre', '/api/v1/cierres-obra', '/api/v1/obras'],
};

export interface Aviso {
  readonly tipo: string;
  readonly datos: Record<string, string>;
}

export type EstadoEnVivo = 'conectando' | 'en-vivo' | 'sin-avisos';

/**
 * Abre el canal mientras el componente esté montado y devuelve su estado.
 *
 * Se monta **una sola vez**, en el shell: dos suscripciones serían dos
 * conexiones abiertas por pestaña y cada aviso invalidaría dos veces.
 */
export function useTiempoReal(): EstadoEnVivo {
  const cliente = useQueryClient();
  const [estado, setEstado] = useState<EstadoEnVivo>('conectando');
  // En una ref y no en estado: cambia en cada reintento y no se pinta.
  const intentos = useRef(0);

  useEffect(() => {
    const control = new AbortController();
    let vivo = true;
    let reloj: ReturnType<typeof setTimeout> | undefined;

    function recargar(aviso: Aviso): void {
      const prefijos = AFECTA[aviso.tipo];
      if (!prefijos) return; // un hecho que esta versión no conoce: se ignora

      void cliente.invalidateQueries({
        predicate: (consulta) => {
          const primera = consulta.queryKey[0];
          const ruta = typeof primera === 'string' ? primera : '';
          return prefijos.some((prefijo) => ruta.includes(prefijo));
        },
      });
    }

    async function escuchar(): Promise<void> {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token || !vivo) return;

      const respuesta = await fetch(`${BASE}${RUTA}`, {
        headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
        signal: control.signal,
      });

      if (!respuesta.ok || !respuesta.body) {
        throw new Error(`El canal respondió ${respuesta.status}`);
      }

      intentos.current = 0;
      if (vivo) setEstado('en-vivo');

      const lector = respuesta.body.pipeThrough(new TextDecoderStream()).getReader();
      let pendiente = '';

      for (;;) {
        const { done, value } = await lector.read();
        if (done || !vivo) return;

        // Un `read()` no entrega mensajes completos: puede cortar a media
        // línea. Se acumula y se procesa solo lo que ya tiene su separador.
        pendiente += value;
        const partes = pendiente.split('\n\n');
        pendiente = partes.pop() ?? '';

        for (const bloque of partes) {
          const aviso = interpretar(bloque);
          if (aviso) recargar(aviso);
        }
      }
    }

    function reintentar(): void {
      if (!vivo) return;
      setEstado('sin-avisos');
      const espera = ESPERAS[Math.min(intentos.current, ESPERAS.length - 1)]!;
      intentos.current += 1;
      reloj = setTimeout(() => void ciclo(), espera);
    }

    async function ciclo(): Promise<void> {
      try {
        await escuchar();
      } catch {
        // Sin distinguir la causa: red caída, 401 por token vencido, deploy en
        // curso. Todas se resuelven igual —esperar y volver a intentar— y el
        // usuario no puede hacer nada distinto con cada una. Que el canal se
        // caiga **no** degrada la app: las pantallas siguen consultando por
        // HTTP, solo dejan de enterarse solas.
      }
      if (vivo) reintentar();
    }

    void ciclo();

    return () => {
      vivo = false;
      clearTimeout(reloj);
      control.abort();
    };
  }, [cliente]);

  return estado;
}

/**
 * Interpreta un bloque SSE (`event:` / `data:` / comentarios).
 *
 * Devuelve `null` para lo que no es un aviso: el latido (`: latido`), el
 * `retry:` inicial y el `conectado` que manda el servidor al abrir. Ninguno
 * de los tres debería invalidar nada.
 */
export function interpretar(bloque: string): Aviso | null {
  const datos = bloque
    .split('\n')
    .filter((linea) => linea.startsWith('data:'))
    .map((linea) => linea.slice(5).trim())
    .join('');

  if (!datos) return null;

  try {
    const aviso = JSON.parse(datos) as Aviso;
    if (!aviso?.tipo || aviso.tipo === 'conectado') return null;
    return { tipo: aviso.tipo, datos: aviso.datos ?? {} };
  } catch {
    // Un bloque que no es JSON no puede tumbar el canal: se descarta y se
    // sigue leyendo el siguiente.
    return null;
  }
}

/** Los hechos que esta versión del cliente sabe atender. Lo usan las pruebas. */
export const HECHOS_CONOCIDOS = Object.keys(AFECTA);
