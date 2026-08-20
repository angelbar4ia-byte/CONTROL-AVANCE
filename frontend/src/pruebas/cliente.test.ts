/**
 * El transporte HTTP — `src/api/cliente.ts`.
 *
 * ## Por qué esta suite existe
 *
 * Las 243 pruebas de web ejercitan reglas puras y **ninguna sale por la red**.
 * Eso dejó pasar dos bugs que habrían roto la aplicación entera contra el
 * backend real:
 *
 * 1. `peticion` anteponía `/api/v1` a rutas que ya lo traían, así que toda
 *    llamada pedía `/api/v1/api/v1/...`.
 * 2. Un `FormData` se serializaba con `JSON.stringify` y se le fijaba
 *    `Content-Type: multipart/form-data` **sin boundary**, que es un multipart
 *    que ningún servidor puede separar.
 *
 * Los dos son invisibles para una prueba de reglas y obvios para una que mira
 * lo que se manda. Aquí se sustituye `fetch` y se inspecciona la petición.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ErrorApi, peticion } from '@/api/cliente';

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'tok-123' } } }),
    },
  },
}));

interface Llamada {
  readonly url: string;
  readonly init: RequestInit;
}

let llamadas: Llamada[] = [];

/**
 * Arma la respuesta que verá `peticion`.
 *
 * `cuerpo` como **string** viaja crudo (para simular un binario); como objeto
 * se serializa a JSON. Aquí no se construye ningún `Blob`, y no es un detalle
 * de estilo: el `Blob` global lo pone jsdom y el `Response` lo pone undici, que
 * no lo reconoce y lo convierte con `String()` — el cuerpo acababa siendo el
 * texto literal `"[object Blob]"`. Pasaba en local por casualidad de versiones
 * y fallaba en CI, que es la peor combinación posible.
 */
function responderCon(cuerpo: unknown, opciones: ResponseInit = {}): void {
  // Un 204 no admite cuerpo: el constructor de `Response` lo rechaza, igual
  // que lo haría un servidor.
  const sinCuerpo = opciones.status === 204;
  const respuesta = new Response(
    sinCuerpo ? null : typeof cuerpo === 'string' ? cuerpo : JSON.stringify(cuerpo),
    {
      status: 200,
      headers: { 'content-type': 'application/json' },
      ...opciones,
    },
  );
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: URL | string, init: RequestInit) => {
      llamadas.push({ url: String(url), init });
      return respuesta;
    }),
  );
}

beforeEach(() => {
  llamadas = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('la ruta que se pide', () => {
  it('no duplica el prefijo del contrato', async () => {
    responderCon({ ok: true });
    await peticion({ url: '/api/v1/usuarios', method: 'GET' });

    expect(llamadas[0]?.url).toContain('/api/v1/usuarios');
    expect(llamadas[0]?.url).not.toContain('/api/v1/api/v1');
  });

  it('lleva el Bearer del JWT', async () => {
    responderCon({ ok: true });
    await peticion({ url: '/api/v1/usuarios', method: 'GET' });

    const cabeceras = llamadas[0]?.init.headers as Record<string, string>;
    expect(cabeceras.Authorization).toBe('Bearer tok-123');
  });

  it('los params vacíos no viajan como "undefined"', async () => {
    responderCon({ ok: true });
    await peticion({
      url: '/api/v1/usuarios',
      method: 'GET',
      params: { rol: 'residente', tipo: undefined, otro: null },
    });

    const url = llamadas[0]?.url ?? '';
    expect(url).toContain('rol=residente');
    expect(url).not.toContain('tipo=');
    expect(url).not.toContain('otro=');
  });
});

describe('cabeceras por llamada', () => {
  it('la pantalla puede mandar su Idempotency-Key', async () => {
    responderCon({ ok: true });
    await peticion(
      { url: '/api/v1/usuarios', method: 'POST', data: { a: 1 } },
      { headers: { 'Idempotency-Key': 'clave-fija' } },
    );

    const cabeceras = llamadas[0]?.init.headers as Record<string, string>;
    expect(cabeceras['Idempotency-Key']).toBe('clave-fija');
  });

  it('lo que manda la pantalla gana sobre lo que fijó el generado', async () => {
    responderCon({ ok: true });
    await peticion(
      {
        url: '/api/v1/x',
        method: 'POST',
        headers: { 'X-Prueba': 'del-generado' },
        data: {},
      },
      { headers: { 'X-Prueba': 'de-la-pantalla' } },
    );

    const cabeceras = llamadas[0]?.init.headers as Record<string, string>;
    expect(cabeceras['X-Prueba']).toBe('de-la-pantalla');
  });
});

describe('multipart', () => {
  it('un FormData se manda tal cual y sin Content-Type', async () => {
    responderCon({ ok: true });
    const formulario = new FormData();
    formulario.append('tipo', 'obras');

    await peticion({ url: '/api/v1/cargas', method: 'POST', data: formulario });

    const { init } = llamadas[0]!;
    // Tal cual: `JSON.stringify(FormData)` da "{}" y el archivo se pierde.
    expect(init.body).toBe(formulario);
    // Sin `Content-Type`: el navegador lo pone con el `boundary`, que es lo
    // único que hace parseable un multipart.
    const cabeceras = init.headers as Record<string, string>;
    expect(cabeceras['Content-Type']).toBeUndefined();
  });

  it('descarta el multipart/form-data sin boundary que declara el generado', async () => {
    responderCon({ ok: true });
    const formulario = new FormData();

    await peticion({
      url: '/api/v1/cargas',
      method: 'POST',
      headers: { 'Content-Type': 'multipart/form-data' },
      data: formulario,
    });

    const cabeceras = llamadas[0]?.init.headers as Record<string, string>;
    expect(cabeceras['Content-Type']).toBeUndefined();
  });

  it('un cuerpo normal sí se serializa como JSON', async () => {
    responderCon({ ok: true });
    await peticion({ url: '/api/v1/x', method: 'POST', data: { a: 1 } });

    expect(llamadas[0]?.init.body).toBe('{"a":1}');
    const cabeceras = llamadas[0]?.init.headers as Record<string, string>;
    expect(cabeceras['Content-Type']).toBe('application/json');
  });
});

describe('descargas binarias', () => {
  it('un xlsx vuelve como archivo con su nombre, no como JSON roto', async () => {
    responderCon('PK', {
      headers: {
        'content-type':
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'content-disposition': 'attachment; filename="plantilla_obras.xlsx"',
      },
    });

    const archivo = await peticion<{ blob: Blob; nombre: string; tipo: string }>({
      url: '/api/v1/cargas/plantillas/obras',
      method: 'GET',
    });

    expect(archivo.nombre).toBe('plantilla_obras.xlsx');
    // Se afirma sobre lo que el objeto **tiene**, no sobre de qué clase es ni
    // sobre métodos opcionales. `toBeInstanceOf(Blob)` pasaba en local y
    // fallaba en CI —el `Blob` global lo pone jsdom y el que devuelve
    // `Response.blob()` lo crea undici: dos clases para el mismo dato— y
    // `.text()` tampoco está en todas las implementaciones. `size` sí, y es lo
    // que prueba que llegaron los bytes en vez de un JSON malinterpretado.
    expect(archivo.blob.size).toBe(2);
    // El tipo sale de la cabecera, no del blob: es lo que decide la rama
    // binaria de `peticion`.
    expect(archivo.tipo).toContain('spreadsheetml');
  });

  it('un nombre con acentos viaja en la forma extendida', async () => {
    responderCon('%PDF', {
      headers: {
        'content-type': 'application/pdf',
        'content-disposition':
          "attachment; filename*=UTF-8''expediente%20t%C3%A9cnico.pdf",
      },
    });

    const archivo = await peticion<{ nombre: string }>({
      url: '/api/v1/obras/x/expediente/pdf',
      method: 'GET',
    });

    expect(archivo.nombre).toBe('expediente técnico.pdf');
  });

  it('sin Content-Disposition hay un nombre usable', async () => {
    responderCon('x', {
      headers: { 'content-type': 'application/octet-stream' },
    });

    const archivo = await peticion<{ nombre: string }>({
      url: '/api/v1/x',
      method: 'GET',
    });

    expect(archivo.nombre).toBe('descarga');
  });
});

describe('errores', () => {
  it('traduce problem+json a ErrorApi', async () => {
    responderCon(
      { type: 'regla-de-identidad', title: 'No permitido', detail: 'Nadie se promueve.' },
      { status: 403 },
    );

    await expect(peticion({ url: '/api/v1/x', method: 'POST' })).rejects.toThrow(
      'Nadie se promueve.',
    );
  });

  it('lleva el status y el tipo, que es lo que la pantalla ramifica', async () => {
    responderCon({ type: 'usuario-no-encontrado', detail: 'No existe.' }, { status: 404 });

    try {
      await peticion({ url: '/api/v1/x', method: 'GET' });
      expect.unreachable('debió lanzar');
    } catch (error) {
      expect(error).toBeInstanceOf(ErrorApi);
      expect((error as ErrorApi).status).toBe(404);
      expect((error as ErrorApi).tipo).toBe('usuario-no-encontrado');
    }
  });

  it('un error en una ruta de descarga sigue siendo un error legible', async () => {
    // El camino feliz de esta ruta devuelve un `.xlsx`, pero el fallo llega
    // como problem+json: si el error se interpretara según el content-type del
    // camino feliz, el operador vería "descarga" en vez del motivo.
    responderCon({ detail: 'La carga no existe.' }, { status: 404 });

    await expect(
      peticion({ url: '/api/v1/cargas/plantillas/obras', method: 'GET' }),
    ).rejects.toThrow('La carga no existe.');
  });

  it('un 204 no intenta leer cuerpo', async () => {
    responderCon(null, { status: 204 });
    await expect(peticion({ url: '/api/v1/x', method: 'DELETE' })).resolves.toBeUndefined();
  });
});

describe('claves por recurso', () => {
  it('dos recursos distintos no comparten clave', async () => {
    // Es el bug que motiva el helper: en una lista, el mismo hook autoriza el
    // cierre 1 y después el 2. Con una clave fija, el backend respondería 422
    // "clave reusada para otra petición" en el segundo.
    const claves = new Map<string, string>();
    const headers = (config: { url: string; method: string }) => {
      const recurso = `${config.method} ${config.url}`;
      if (!claves.has(recurso)) claves.set(recurso, `clave-${claves.size}`);
      return { 'Idempotency-Key': claves.get(recurso)! };
    };

    responderCon({ ok: true });
    await peticion({ url: '/api/v1/cierres/1/autorizar', method: 'POST' }, { headers });
    await peticion({ url: '/api/v1/cierres/2/autorizar', method: 'POST' }, { headers });
    // El reintento del primero: misma clave, que es para lo que sirve.
    await peticion({ url: '/api/v1/cierres/1/autorizar', method: 'POST' }, { headers });

    const enviadas = llamadas.map(
      (l) => (l.init.headers as Record<string, string>)['Idempotency-Key'],
    );
    expect(enviadas[0]).not.toBe(enviadas[1]);
    expect(enviadas[0]).toBe(enviadas[2]);
  });
});
