-- ============================================================
-- ObraCtrl · 0025 · Nadie se promueve a sí mismo
-- Spec §12.4 (RLS es la frontera) · §4 (roles) · §5.1 (alta la hace Control de
-- obra) · Fase 7 del ROADMAP.
--
-- DOS AGUJEROS QUE APARECIERON AL IR A ABRIR LA PANTALLA DE USUARIOS
--
-- **1. Cualquiera podía cambiar su propio rol.** La política
-- `usuario_self_update` (0012) existe para que cada quien edite su perfil
-- —teléfono, cédula— y dice:
--
--     using (id = app.current_usuario_id()) with check (id = app.current_usuario_id())
--
-- RLS filtra **filas**, no columnas. La fila propia sigue siendo la fila propia
-- después de un `update usuario set rol = 'super_intendente' where id = <yo>`,
-- así que el `with check` pasa y la escalada se consuma. Por la ruta directa a
-- Supabase (§10.7) eso es una sentencia desde el navegador.
--
-- **2. Control de obra podía fabricar un Super intendente.** La política de
-- escritura de `usuario` es `app.es_config()`, que incluye a `control_obra`
-- —correcto, es quien da de alta (§5.1)—, pero nada le impedía darle al alta
-- el rol de más privilegio, ni promover a otro después.
--
-- Ninguno de los dos se arregla con una política: hacen falta reglas **por
-- columna y por transición**, y eso es un trigger. Va en la base y no en el
-- backend a propósito: es la única frontera que también cubre la ruta directa
-- y el `UPDATE` a mano en el dashboard (§12.4).
--
-- SIN CONTEXTO NO SE APLICA, Y ESO ES DELIBERADO
--
-- Cuando `app.current_usuario_id()` es nulo no hay sesión de aplicación: es una
-- semilla, una migración o un `psql` de mantenimiento corriendo como dueño. Ahí
-- el guardia no aplica, igual que RLS no aplica al owner. Quien tiene la
-- cadena de conexión de superusuario ya puede todo; fingir lo contrario sería
-- teatro.
-- ============================================================

-- ------------------------------------------------------------
-- Contraseña temporal: el alta la fija Control de obra (§5.1), así que la
-- persona tiene que cambiarla al entrar. La bandera vive aquí y no en el
-- metadata de Supabase para que el backend pueda exigirla sin ir al proveedor
-- de auth en cada petición.
-- ------------------------------------------------------------
alter table usuario
  add column debe_cambiar_password boolean not null default false;

comment on column usuario.debe_cambiar_password is
  'La contraseña vigente la eligió alguien más (alta con contraseña temporal, §5.1). La web obliga a cambiarla antes de dejar trabajar. La apaga el propio usuario al cambiarla.';

-- ------------------------------------------------------------
-- Guardia
-- ------------------------------------------------------------
create or replace function app.usuario_guardia_de_privilegios()
returns trigger
language plpgsql
security definer
set search_path = public, app, pg_temp
as $$
declare
  v_yo  uuid := app.current_usuario_id();
  v_rol text := app.current_rol();
begin
  -- Sin sesión de aplicación no hay a quién limitar: ver el encabezado.
  if v_yo is null then
    return new;
  end if;

  if tg_op = 'INSERT' then
    -- Solo el que ya es Super intendente puede crear a otro. Si no, Control de
    -- obra se daría a sí mismo un cómplice con más privilegios que él.
    if new.rol = 'super_intendente' and v_rol is distinct from 'super_intendente' then
      raise exception
        'Solo un super intendente puede dar de alta a otro super intendente (§4).'
        using errcode = 'insufficient_privilege';
    end if;
    return new;
  end if;

  -- A partir de aquí, UPDATE.

  -- La organización de un usuario no cambia. Moverlo de organización es darlo
  -- de baja y volverlo a crear: el `org_id` viaja en el JWT y en cada fila que
  -- esa persona escribió.
  if new.org_id is distinct from old.org_id then
    raise exception 'El org_id de un usuario no se cambia (§12.4).'
      using errcode = 'insufficient_privilege';
  end if;

  -- La cuenta del proveedor de auth se liga una vez, al alta. Repuntarla a
  -- otra sería entregarle la identidad de esta persona a quien controle esa
  -- otra cuenta.
  if new.auth_user_id is distinct from old.auth_user_id
     and old.auth_user_id is not null then
    raise exception 'La cuenta de autenticación ya está ligada y no se repunta.'
      using errcode = 'insufficient_privilege';
  end if;

  if new.id = v_yo then
    -- Editar el perfil propio, sí. Promoverse o reactivarse, no.
    if new.rol is distinct from old.rol then
      raise exception 'Nadie cambia su propio rol (§4).'
        using errcode = 'insufficient_privilege';
    end if;
    if new.estatus is distinct from old.estatus then
      raise exception 'Nadie cambia su propio estatus (§4).'
        using errcode = 'insufficient_privilege';
    end if;
    return new;
  end if;

  -- Cambiar el rol de alguien más: nunca hacia o desde super intendente si
  -- quien lo hace no lo es. "Desde" también, porque degradar al único super
  -- intendente es la otra mitad del mismo problema.
  if new.rol is distinct from old.rol
     and 'super_intendente' in (new.rol::text, old.rol::text)
     and v_rol is distinct from 'super_intendente' then
    raise exception
      'Solo un super intendente puede otorgar o retirar el rol de super intendente (§4).'
      using errcode = 'insufficient_privilege';
  end if;

  return new;
end;
$$;

comment on function app.usuario_guardia_de_privilegios() is
  'Reglas por columna que RLS no puede expresar: nadie cambia su propio rol ni su estatus, el org_id es inmutable, la cuenta de auth se liga una sola vez, y el rol de super intendente solo lo mueve otro super intendente (§4, §12.4).';

create trigger trg_usuario_guardia_de_privilegios
  before insert or update on public.usuario
  for each row execute function app.usuario_guardia_de_privilegios();
