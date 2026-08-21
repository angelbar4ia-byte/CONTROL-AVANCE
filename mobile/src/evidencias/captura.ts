/**
 * Tomar la foto y dejarla a salvo antes de encolarla (§12.5).
 *
 * ## Por qué se copia el archivo
 *
 * `expo-image-picker` devuelve un `file://` que vive en el **caché** de la
 * app —de la cámara o de la copia temporal que hace de la galería—. El
 * sistema puede vaciar ese caché cuando le falta espacio, y en un teléfono de
 * obra con la memoria llena eso pasa. Si la foto sigue en la cola cuando se
 * borra, la subida falla con "el archivo ya no está" y la evidencia se
 * perdió: se sacó, pero nunca llegó.
 *
 * Copiarla a `documentDirectory` la saca de esa categoría. Ahí solo se borra
 * cuando la app lo pide —`purgarSubidas`, ya con el objeto en R2— o cuando el
 * usuario limpia los datos de la app.
 *
 * ## Por qué image-picker y no una pantalla de cámara propia
 *
 * `expo-camera` está en las dependencias y permite una UI a medida, pero
 * `launchCameraAsync` da la cámara del sistema: la que el usuario ya sabe
 * usar, con su flash, su enfoque y su rotación resueltos. Una cámara propia
 * solo se justifica cuando hay que dibujar algo encima —un encuadre, un
 * medidor—, y aquí no hay nada de eso.
 */

import * as FileSystem from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';

import { generarId } from '@/lib/id';

/** Dónde viven las fotos ya a salvo del vaciado de caché. */
const CARPETA = `${FileSystem.documentDirectory}evidencias/`;

/**
 * Calidad de compresión. 0.7 y no 1: una foto de obra a calidad plena son 4-6
 * MB, y subir eso por datos móviles desde una obra sin wifi es la diferencia
 * entre que la evidencia llegue hoy o la semana que viene. A 0.7 se sigue
 * distinguiendo un acabado mal rematado, que es para lo que sirve.
 */
const CALIDAD = 0.7;

export interface FotoTomada {
  readonly uri: string;
  readonly nombre: string;
  readonly contentType: string;
}

export type Origen = 'camara' | 'galeria';

/**
 * Abre la cámara o la galería y devuelve la foto ya copiada a un lugar
 * estable. `null` si el usuario canceló o negó el permiso — cancelar no es un
 * error y no debe mostrar nada.
 */
export async function tomarFoto(origen: Origen): Promise<FotoTomada | null> {
  const permiso =
    origen === 'camara'
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();

  if (!permiso.granted) return null;

  const opciones: ImagePicker.ImagePickerOptions = {
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: CALIDAD,
    // Sin edición: recortar una evidencia es justo lo que no se quiere que
    // pase entre la obra y el expediente (§7.9).
    allowsEditing: false,
    exif: false,
  };

  const resultado =
    origen === 'camara'
      ? await ImagePicker.launchCameraAsync(opciones)
      : await ImagePicker.launchImageLibraryAsync(opciones);

  const activo = resultado.assets?.[0];
  if (resultado.canceled || !activo) return null;

  return guardarLocal(activo.uri, activo.mimeType ?? 'image/jpeg');
}

/** Copia el archivo a `documentDirectory/evidencias/` con un nombre único. */
async function guardarLocal(uriOrigen: string, contentType: string): Promise<FotoTomada> {
  await FileSystem.makeDirectoryAsync(CARPETA, { intermediates: true }).catch(() => {
    // `intermediates: true` ya es idempotente; el catch cubre la carrera de
    // dos capturas simultáneas creando la carpeta a la vez.
  });

  const nombre = `${new Date().toISOString().slice(0, 10)}-${generarId()}.${extension(contentType)}`;
  const destino = `${CARPETA}${nombre}`;

  await FileSystem.copyAsync({ from: uriOrigen, to: destino });

  return { uri: destino, nombre, contentType };
}

function extension(contentType: string): string {
  if (contentType.includes('png')) return 'png';
  if (contentType.includes('webp')) return 'webp';
  if (contentType.includes('heic')) return 'heic';
  return 'jpg';
}
