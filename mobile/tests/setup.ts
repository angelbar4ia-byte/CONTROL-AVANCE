/**
 * Preparación común de las pruebas del móvil.
 *
 * Lo que se simula aquí es **infraestructura del dispositivo**, no lógica:
 * el almacenamiento seguro, la cámara, el sistema de archivos y el cliente de
 * Supabase. Nada de esto existe en Node, y simularlo en cada archivo de
 * prueba llevaría a cuatro versiones distintas del mismo doble.
 *
 * Lo que **no** se simula: las reglas de captura (§6), la comparación de
 * versiones (§12.12) ni la clasificación de errores de las colas. Esas son la
 * lógica que se está probando y se ejercitan de verdad.
 */

// `expo-secure-store` toca el llavero del sistema; en Node no hay ninguno.
jest.mock('expo-secure-store', () => {
  const almacen = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (clave: string) => almacen.get(clave) ?? null),
    setItemAsync: jest.fn(async (clave: string, valor: string) => {
      almacen.set(clave, valor);
    }),
    deleteItemAsync: jest.fn(async (clave: string) => {
      almacen.delete(clave);
    }),
  };
});

// El cliente real intentaría alcanzar la red al construirse.
jest.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: jest.fn(async () => ({
        data: { session: { access_token: 'token-de-prueba', expires_at: 0 } },
        error: null,
      })),
    },
  },
}));

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///documentos/',
  getInfoAsync: jest.fn(async () => ({ exists: true, size: 1024 })),
  copyAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  makeDirectoryAsync: jest.fn(async () => undefined),
  uploadAsync: jest.fn(async () => ({ status: 200, body: '' })),
  FileSystemUploadType: { BINARY_CONTENT: 0 },
}));
