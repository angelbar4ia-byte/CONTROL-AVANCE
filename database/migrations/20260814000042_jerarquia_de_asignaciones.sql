-- ============================================================
-- ObraCtrl · 0042 · La cadena de mando se vuelve el alcance
-- Spec §4 (roles y alcance) · §5.1 ("Equipo" · "Asignaciones") · §12.4 (RLS) ·
-- §10.7 (ruta directa a Supabase: RLS es la única frontera)
--
-- POR QUÉ EL CAMBIO
--
-- El usuario describió su organización así, textual: "todos están asignados a
-- Control, los residentes y supervisores a superintendente, los residentes a
-- los supervisores y las obras a los residentes. Por tanto pueden ser varios
-- proyectos, clusters y obras para los usuarios".
--
-- Eso es una CADENA:
--
--     Control de obra → Super intendente → Supervisor → Residente → Obra
--
-- y esa cadena INVIERTE el modelo que traía el esquema desde la 0011:
--
--   · `control_obra` estaba acotado a los proyectos de `control_proyecto`;
--     ahora es el rol de arriba y ve la organización completa.
--   · `super_intendente` era el que veía toda la organización sin puente
--     ninguno (así lo decía el `comment on table control_proyecto`); ahora
--     cuelga de Control y ve solo lo de la gente que tiene asignada.
--
-- Y el alcance de cada nivel intermedio **sigue a las personas, no al
-- territorio**. Textual otra vez, sobre el supervisor: "Las obras de sus
-- residentes. El alcance sigue a la gente: si le asignas un residente, ve las
-- obras de ese residente. Al mover un residente, su cartera lo sigue."
--
-- LOS TRES PUENTES NUEVOS, Y POR QUÉ SON TRES Y NO UNO
--
-- Se podría haber hecho una sola tabla `asignacion(jefe_id, subordinado_id)`
-- polimórfica. No se hace: cada puente une cosas de tipo distinto —persona con
-- persona en dos de ellos, persona con obra en el tercero— y una tabla única
-- perdería las llaves foráneas que hoy garantizan que no quede una asignación
-- apuntando a una obra borrada. Las FK son la mitad de la garantía; la otra
-- mitad son las políticas, y esas también difieren puente por puente.
--
--   · `superintendente_usuario` — el SI y su gente (supervisores Y residentes:
--     el usuario dijo "los residentes y supervisores a superintendente", o sea
--     que un residente puede colgar del SI sin supervisor de por medio).
--   · `supervisor_residente`    — el supervisor y sus residentes.
--   · `residente_obra`          — el residente y sus obras. M2M: "SON VARIOS
--     RESIDENTES PARA VARIAS OBRAS, UN RESIDENTE PUEDE LLEVAR VARIAS OBRAS".
--
-- Los tres son M2M sin excepción, que es lo que el usuario pidió en la cuarta
-- respuesta ("pueden ser varios proyectos, clusters y obras para los
-- usuarios").
--
-- QUÉ PASA CON LO QUE YA EXISTÍA
--
-- · `obra.residente_id` SE CONSERVA. Tiene datos reales y la leen RLS vieja,
--   `generar_obra_desde_prototipo`, cinco repos, la regla de dominio de
--   cierres, las notificaciones y las sync rules de PowerSync. Pasa a ser **el
--   residente principal** —una etiqueta, ya no la frontera— y se mantiene en
--   sincronía con `residente_obra` con triggers en los dos sentidos (abajo).
--   Quien la lee sigue leyendo lo mismo; quien decide qué se ve es el puente.
--
-- · `control_proyecto` QUEDA INERTE PARA EL ALCANCE. Control ve toda la
--   organización, así que el puente ya no acota nada. No se borra —tiene datos
--   y políticas colgando, y borrarla haría irreversible este despliegue— ni se
--   deja de escribir: el trigger de la 0016 la sigue llenando, y esa fila es
--   hoy el registro de "qué proyectos abrió/atiende este Control", útil para
--   la pantalla de Asignaciones aunque ya no gobierne quién ve qué.
--
-- · `supervisor_cluster` DEJA DE ALIMENTAR RLS. El alcance del supervisor ya
--   no es su manzana sino su gente. La tabla se conserva como dato
--   territorial —qué clusters recorre— y como origen del relleno de abajo.
--
-- EL RELLENO NO PUEDE DEJAR A NADIE SIN VER SU TRABAJO
--
-- Esta migración corre contra una base con obras y usuarios reales. Las tres
-- cargas de abajo derivan el modelo nuevo del viejo de forma que nadie pierda
-- de golpe lo que hoy ve; lo único que se estrecha es lo que el usuario pidió
-- estrechar (el super intendente), y aun ahí se rellena con toda su gente para
-- que el día del corte no cambie nada y sea un humano quien decida a quién
-- quitarle.
-- ============================================================

-- ------------------------------------------------------------
-- 1 · Los puentes
-- ------------------------------------------------------------

create table superintendente_usuario (
  id                  uuid primary key default gen_random_uuid(),
  org_id              uuid not null references organizacion(id) on delete cascade,
  superintendente_id  uuid not null references usuario(id) on delete cascade,
  usuario_id          uuid not null references usuario(id) on delete cascade,
  created_at          timestamptz not null default now(),
  constraint uq_superintendente_usuario unique (superintendente_id, usuario_id),
  -- Sin esto, `superintendente_id = usuario_id` sería una fila legal que no
  -- amplía nada pero ensucia todo recorrido del árbol de mando.
  constraint ck_superintendente_usuario_distintos
    check (superintendente_id <> usuario_id)
);
create index ix_superintendente_usuario_si  on superintendente_usuario (org_id, superintendente_id);
create index ix_superintendente_usuario_usr on superintendente_usuario (org_id, usuario_id);

comment on table superintendente_usuario is
  'Puente Super intendente -> su gente (supervisores y residentes), §4. Desde la 0042 el SI ya NO ve toda la organización: ve exactamente lo de las personas que aparecen aquí, directas o a través de sus supervisores.';
comment on column superintendente_usuario.usuario_id is
  'Un supervisor o un residente. Los dos caben a propósito: el usuario pidió "los residentes y supervisores a superintendente", o sea que un residente puede colgar del SI sin supervisor de por medio.';

create table supervisor_residente (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  supervisor_id uuid not null references usuario(id) on delete cascade,
  residente_id  uuid not null references usuario(id) on delete cascade,
  created_at    timestamptz not null default now(),
  constraint uq_supervisor_residente unique (supervisor_id, residente_id),
  constraint ck_supervisor_residente_distintos
    check (supervisor_id <> residente_id)
);
create index ix_supervisor_residente_sup on supervisor_residente (org_id, supervisor_id);
create index ix_supervisor_residente_res on supervisor_residente (org_id, residente_id);

comment on table supervisor_residente is
  'Puente Supervisor -> sus residentes (§4). Sustituye a supervisor_cluster como fuente del alcance: "el alcance sigue a la gente: al mover un residente, su cartera lo sigue". supervisor_cluster se conserva como dato territorial, ya no gobierna RLS.';

create table residente_obra (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizacion(id) on delete cascade,
  residente_id  uuid not null references usuario(id) on delete cascade,
  obra_id       uuid not null references obra(id) on delete cascade,
  created_at    timestamptz not null default now(),
  constraint uq_residente_obra unique (residente_id, obra_id)
);
create index ix_residente_obra_res  on residente_obra (org_id, residente_id);
create index ix_residente_obra_obra on residente_obra (org_id, obra_id);

comment on table residente_obra is
  'Puente Residente -> sus obras (§4). Es la FUENTE DE VERDAD del alcance de obra desde la 0042; obra.residente_id queda como el residente principal y se mantiene en sincronía con triggers. M2M porque el usuario lo pidió así: "SON VARIOS RESIDENTES PARA VARIAS OBRAS, UN RESIDENTE PUEDE LLEVAR VARIAS OBRAS".';

grant select, insert, update, delete
  on superintendente_usuario, supervisor_residente, residente_obra
  to authenticated, obractrl_api;

-- ------------------------------------------------------------
-- 2 · Relleno de lo que ya existe
--
-- Corre ANTES de cambiar las políticas, y como owner (bypassa RLS): es
-- reconciliación de datos, no operación de un usuario.
--
-- Y corre ANTES de crear los triggers de sincronía (sección 3), lo cual es
-- deliberado y no un accidente del orden del archivo: la carga 2.a copia
-- `obra.residente_id` hacia `residente_obra`, así que con el trigger de vuelta
-- ya montado cada fila insertada dispararía un `update obra` que solo volvería
-- a escribir el valor que ya estaba. En una base con miles de obras eso es un
-- trigger por fila para no cambiar nada. Al terminar la sección 2 las dos
-- representaciones ya son consistentes, que es justo la condición de la que
-- parten los triggers.
-- ------------------------------------------------------------

-- 2.a · Residente -> obra, desde la columna que hasta hoy era la frontera.
-- Es una traducción exacta: cada obra con residente queda con su fila.
insert into residente_obra (org_id, residente_id, obra_id)
select o.org_id, o.residente_id, o.id
  from obra o
 where o.residente_id is not null
on conflict (residente_id, obra_id) do nothing;

-- 2.b · Supervisor -> residentes, derivado de su territorio actual.
-- El supervisor que hoy ve un cluster ve las obras de ese cluster; mañana verá
-- las obras de sus residentes. Se le asignan los residentes que HOY tienen
-- obra en sus clusters, que es el conjunto que reproduce su vista actual.
--
-- LO QUE SÍ SE PIERDE, Y HAY QUE DECIRLO: una obra de su cluster **sin
-- residente asignado** no tiene por dónde llegar al modelo nuevo y deja de
-- verla. No es un descuido — es que en el modelo nuevo esa obra no cuelga de
-- nadie. La ve Control (org completa) y se arregla asignándole residente.
insert into supervisor_residente (org_id, supervisor_id, residente_id)
select distinct sc.org_id, sc.supervisor_id, o.residente_id
  from supervisor_cluster sc
  join obra o
    on o.cluster_id = sc.cluster_id
   and o.org_id = sc.org_id
 where o.residente_id is not null
   and o.residente_id <> sc.supervisor_id
on conflict (supervisor_id, residente_id) do nothing;

-- 2.c · Super intendente -> toda su gente.
-- Aquí no hay de dónde derivar: el SI nunca tuvo puente porque su alcance era
-- la organización entera. Dejarlo vacío lo dejaría CIEGO el día del
-- despliegue, que es exactamente el modo de falla que no se puede permitir. Se
-- le asigna todo supervisor y residente de su organización: eso reproduce
-- literalmente lo que ve hoy y no le concede nada nuevo. A partir de ahí,
-- estrechar es una decisión humana en la pantalla de Asignaciones, no un
-- efecto colateral de un deploy.
insert into superintendente_usuario (org_id, superintendente_id, usuario_id)
select si.org_id, si.id, u.id
  from usuario si
  join usuario u
    on u.org_id = si.org_id
   and u.rol in ('supervisor', 'residente')
 where si.rol = 'super_intendente'
on conflict (superintendente_id, usuario_id) do nothing;

-- ------------------------------------------------------------
-- 3 · Sincronía obra.residente_id <-> residente_obra
--
-- La columna se queda y el puente manda. Para que las dos digan lo mismo sin
-- que nadie tenga que acordarse, se sincronizan con triggers en los dos
-- sentidos. Ambos son `security definer` por la misma razón que el de la 0016:
-- el dueño de la tabla no pasa por RLS, así que el trigger puede escribir el
-- puente sin ampliarle a nadie sus permisos.
--
-- POR QUÉ EL UPDATE MUEVE Y NO SUMA
--
-- `update obra set residente_id = B` donde antes había A significa, en toda la
-- app y en la cabeza de quien lo escribe, "ahora la lleva B". Si el trigger
-- solo agregara a B, A conservaría el alcance para siempre sin que nadie lo
-- haya decidido: una concesión silenciosa de permisos. Se mueve.
--
-- Los dos triggers no se ciclan: el `on conflict do nothing` y los `is
-- distinct from` cortan la recursión en el primer rebote (una escritura que no
-- cambia nada no dispara nada).
-- ------------------------------------------------------------

create or replace function app.sincronizar_residente_de_obra()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if tg_op = 'UPDATE'
     and old.residente_id is not null
     and new.residente_id is distinct from old.residente_id then
    delete from residente_obra
     where obra_id = new.id
       and residente_id = old.residente_id;
  end if;

  if new.residente_id is not null
     and (tg_op = 'INSERT' or new.residente_id is distinct from old.residente_id) then
    insert into residente_obra (org_id, residente_id, obra_id)
    values (new.org_id, new.residente_id, new.id)
    on conflict (residente_id, obra_id) do nothing;
  end if;

  return null;
end;
$$;

comment on function app.sincronizar_residente_de_obra() is
  'obra.residente_id -> residente_obra (0042). Mantiene el puente al día para todo el código que sigue asignando residente desde la obra.';

create trigger trg_obra_sincronizar_residente
  after insert or update of residente_id on public.obra
  for each row execute function app.sincronizar_residente_de_obra();

create or replace function app.sincronizar_obra_de_residente()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_relevo uuid;
begin
  if tg_op = 'INSERT' then
    -- El primero en llegar se vuelve el principal. Si ya hay uno, no se le
    -- quita: agregar un segundo residente a la obra no es destituir al primero.
    update obra
       set residente_id = new.residente_id
     where id = new.obra_id
       and residente_id is null;
    return null;
  end if;

  -- DELETE: si el que se va era el principal, la etiqueta pasa a cualquiera de
  -- los que quedan; si no queda ninguno, se vacía. Dejar apuntando a alguien
  -- que ya no lleva la obra sería peor que dejarla nula: los repos y las
  -- notificaciones leen esa columna.
  select ro.residente_id into v_relevo
    from residente_obra ro
   where ro.obra_id = old.obra_id
   order by ro.created_at, ro.id
   limit 1;

  update obra
     set residente_id = v_relevo
   where id = old.obra_id
     and residente_id = old.residente_id;

  return null;
end;
$$;

comment on function app.sincronizar_obra_de_residente() is
  'residente_obra -> obra.residente_id (0042). Mantiene viva la etiqueta de residente principal para los consumidores que aún leen la columna.';

create trigger trg_residente_obra_sincronizar_principal
  after insert or delete on public.residente_obra
  for each row execute function app.sincronizar_obra_de_residente();

-- ------------------------------------------------------------
-- 4 · Helpers de alcance, reescritos al modelo nuevo
-- ------------------------------------------------------------

create or replace function app.es_control()
returns boolean
language sql
stable
as $$
  select app.current_rol() = 'control_obra'
$$;

comment on function app.es_control() is
  'El rol de arriba de la cadena (§4, desde la 0042): ve y administra la organización completa. Distinto de app.es_config(), que sigue siendo "C y SI" para catálogos y cargas.';

-- Los residentes de un super intendente: los que le cuelgan directo más los de
-- sus supervisores. Se aísla en su propia función porque aparece en cuatro
-- predicados y repetir la unión en cada uno es la forma segura de que un día
-- discrepen.
create or replace function app.residentes_del_superintendente(p_si uuid)
returns table (residente_id uuid)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select su.usuario_id
    from superintendente_usuario su
   where su.superintendente_id = p_si
  union
  select sr.residente_id
    from superintendente_usuario su
    join supervisor_residente sr on sr.supervisor_id = su.usuario_id
   where su.superintendente_id = p_si
$$;

comment on function app.residentes_del_superintendente(uuid) is
  'La primera rama devuelve también supervisores (usuario_id puede ser uno): es inocuo porque un supervisor no tiene filas en residente_obra, y evita una segunda consulta para separarlos.';

-- ¿La persona `p_usuario_id` está bajo el mando de quien pregunta? Gobierna
-- quién puede tocar los puentes, no quién ve obras.
create or replace function app.usuario_en_alcance(p_usuario_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_usuario_id is null then
    return false;
  end if;

  if not exists (
    select 1 from usuario u
     where u.id = p_usuario_id and u.org_id = v_org
  ) then
    return false;
  end if;

  -- Control es el de arriba: toda la organización es su gente.
  if v_rol = 'control_obra' then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'super_intendente' then
    return exists (
      select 1 from superintendente_usuario su
       where su.superintendente_id = v_usr
         and su.usuario_id = p_usuario_id
    );
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1 from supervisor_residente sr
       where sr.supervisor_id = v_usr
         and sr.residente_id = p_usuario_id
    );
  end if;

  -- Un residente no manda a nadie; se alcanza a sí mismo y ya.
  return p_usuario_id = v_usr;
end;
$$;

comment on function app.usuario_en_alcance(uuid) is
  'Cadena de mando del §4 (0042): ¿esta persona cuelga de quien pregunta? Gobierna la ESCRITURA de los puentes de asignación. Para el super intendente son sus asignados directos, no los residentes de sus supervisores: reasignar al residente de otro es trabajo del supervisor de ese residente o de Control.';

-- ------------------------------------------------------------
-- Alcance por rol (§4), modelo 0042:
--   control_obra     -> toda la organización
--   super_intendente -> obras de su gente (directa o vía sus supervisores)
--   supervisor       -> obras de sus residentes
--   residente        -> sus obras (residente_obra)
-- ------------------------------------------------------------
create or replace function app.obra_visible(p_obra_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_obra_id is null then
    return false;
  end if;

  if not exists (
    select 1 from obra o
     where o.id = p_obra_id and o.org_id = v_org
  ) then
    return false;
  end if;

  -- Control ve la organización completa. Es el único rol que no necesita
  -- puente, y es deliberado: alguien tiene que poder rescatar una obra que
  -- quedó sin residente, y ese alguien es el de arriba.
  if v_rol = 'control_obra' then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'residente' then
    return exists (
      select 1 from residente_obra ro
       where ro.obra_id = p_obra_id
         and ro.residente_id = v_usr
    );
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1
        from supervisor_residente sr
        join residente_obra ro on ro.residente_id = sr.residente_id
       where sr.supervisor_id = v_usr
         and ro.obra_id = p_obra_id
    );
  end if;

  if v_rol = 'super_intendente' then
    return exists (
      select 1
        from app.residentes_del_superintendente(v_usr) r
        join residente_obra ro on ro.residente_id = r.residente_id
       where ro.obra_id = p_obra_id
    );
  end if;

  return false;
end;
$$;

comment on function app.obra_visible(uuid) is
  'Frontera de alcance por rol (§4), modelo 0042: Control -> toda la org; SI -> obras de su gente; supervisor -> obras de sus residentes; residente -> sus obras. Las sync rules de PowerSync deben reflejar exactamente esta misma lógica (§12.4).';

-- ------------------------------------------------------------
-- Proyecto y cluster son ESTRUCTURA, no operación.
--
-- Control y Super intendente los ven completos; supervisor y residente los
-- derivan de sus obras, como hasta hoy.
--
-- POR QUÉ EL SI CONSERVA LA ESTRUCTURA COMPLETA SI YA NO VE TODAS LAS OBRAS
--
-- Porque no le concede NADA operativo: obra, actividad, avance, estimación,
-- incidencia, cierre, expediente y revisión cuelgan todos de
-- `app.obra_visible()`, que sí se cerró. Lo que ve aquí son los nombres de los
-- proyectos y las manzanas de su propia organización — el mismo nivel que los
-- catálogos que ya administra con `app.es_config()`.
--
-- Y porque cerrarlo abriría el agujero que la 0016 tuvo que tapar para
-- Control: `proyecto_insert` es `es_config()` (el SI puede crear proyectos),
-- así que si `proyecto_visible` dependiera de sus obras, un SI crearía un
-- proyecto y no lo volvería a ver — sin trigger que lo rescate, porque no hay
-- puente SI->proyecto que rellenar.
-- ------------------------------------------------------------
create or replace function app.proyecto_visible(p_proyecto_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_proyecto_id is null then
    return false;
  end if;

  if not exists (
    select 1 from proyecto p
     where p.id = p_proyecto_id and p.org_id = v_org
  ) then
    return false;
  end if;

  if v_rol in ('control_obra', 'super_intendente') then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  if v_rol = 'supervisor' then
    return exists (
      select 1
        from supervisor_residente sr
        join residente_obra ro on ro.residente_id = sr.residente_id
        join obra o           on o.id = ro.obra_id
        join cluster c        on c.id = o.cluster_id
       where sr.supervisor_id = v_usr
         and c.proyecto_id = p_proyecto_id
    );
  end if;

  if v_rol = 'residente' then
    return exists (
      select 1
        from residente_obra ro
        join obra o    on o.id = ro.obra_id
        join cluster c on c.id = o.cluster_id
       where ro.residente_id = v_usr
         and c.proyecto_id = p_proyecto_id
    );
  end if;

  return false;
end;
$$;

-- Alcance evaluado sobre el CLUSTER, no sobre la obra. Sigue existiendo por la
-- misma razón de la 0011: en un INSERT la fila nueva todavía no es visible bajo
-- el snapshot de una función STABLE, así que un predicado que consulte `obra`
-- por su propio id rechazaría toda alta.
create or replace function app.cluster_en_alcance(p_cluster_id uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
  v_org uuid := app.current_org_id();
  v_usr uuid := app.current_usuario_id();
  v_rol rol_usuario := app.current_rol();
begin
  if v_org is null or p_cluster_id is null then
    return false;
  end if;

  if not exists (
    select 1 from cluster c
     where c.id = p_cluster_id and c.org_id = v_org
  ) then
    return false;
  end if;

  if v_rol in ('control_obra', 'super_intendente') then
    return true;
  end if;

  if v_usr is null then
    return false;
  end if;

  -- Al supervisor se le acota a los clusters donde YA tiene obra visible: no
  -- puede mover una obra suya a una manzana ajena y arrastrar su alcance.
  if v_rol = 'supervisor' then
    return exists (
      select 1
        from supervisor_residente sr
        join residente_obra ro on ro.residente_id = sr.residente_id
        join obra o           on o.id = ro.obra_id
       where sr.supervisor_id = v_usr
         and o.cluster_id = p_cluster_id
    );
  end if;

  return false;
end;
$$;

-- ------------------------------------------------------------
-- 5 · ¿Quién puede repartir a quién?
--
-- La regla que sostiene todo esto es una sola, y conviene decirla entera
-- porque es la que evita la escalada de privilegios:
--
--   METER TRABAJO NUEVO A LA CADENA ES DE CONTROL. Los niveles intermedios
--   solo REPARTEN lo que ya tienen.
--
-- Si un supervisor pudiera asignarle a un residente suyo una obra cualquiera,
-- se ampliaría su propio alcance —el alcance del supervisor ES el de sus
-- residentes— con solo escribir una fila. Por eso su permiso exige que la obra
-- ya le sea visible: repartir dentro de su cartera, sí; traerse una ajena, no.
-- Lo mismo aplica al super intendente un nivel arriba. Control no tiene ese
-- límite porque ya ve todo: no hay nada que pueda ampliarse.
--
-- Es la misma lógica por la que la 0012 dejaba `control_proyecto` solo en
-- manos del SI, movida un piso hacia arriba junto con la jerarquía.
-- ------------------------------------------------------------

create or replace function app.puede_repartir_obra(p_residente_id uuid, p_obra_id uuid)
returns boolean
language sql
stable
as $$
  select case
    when app.es_control() then app.usuario_en_alcance(p_residente_id)
    when app.current_rol() in ('super_intendente', 'supervisor')
      then app.usuario_en_alcance(p_residente_id) and app.obra_visible(p_obra_id)
    else false
  end
$$;

comment on function app.puede_repartir_obra(uuid, uuid) is
  'Escritura de residente_obra (§4, 0042). Los mandos intermedios reparten dentro de su cartera; traer una obra nueva a la cadena es de Control. Sin esto, un supervisor se ampliaría el alcance escribiendo una fila.';

alter table superintendente_usuario enable row level security;
alter table supervisor_residente    enable row level security;
alter table residente_obra          enable row level security;

-- Lectura de los puentes: quien configura, y quien aparece en la fila. Un
-- residente puede ver de quién depende y qué obras lleva; un supervisor, la
-- cartera de sus residentes. Nadie ve el organigrama de otra rama.
create policy superintendente_usuario_select on superintendente_usuario
  for select using (
    org_id = app.current_org_id()
    and (app.es_config()
         or superintendente_id = app.current_usuario_id()
         or usuario_id = app.current_usuario_id())
  );

-- Escritura: SOLO Control. Esta tabla define el alcance del Super intendente,
-- o sea el alcance de quien administra; si el SI pudiera editarla se ampliaría
-- a sí mismo. Es literalmente la regla que la 0012 le aplicaba a
-- `control_proyecto`, un piso más arriba.
select app.crear_policies_escritura(
  'superintendente_usuario',
  'org_id = app.current_org_id() and app.es_control()');

create policy supervisor_residente_select on supervisor_residente
  for select using (
    org_id = app.current_org_id()
    and (app.es_config()
         or supervisor_id = app.current_usuario_id()
         or residente_id = app.current_usuario_id())
  );

-- Escritura: Control siempre; el Super intendente solo dentro de su gente —el
-- supervisor y el residente tienen que colgar los dos de él—. El supervisor no
-- se auto-asigna residentes por la misma razón de siempre.
select app.crear_policies_escritura(
  'supervisor_residente',
  'org_id = app.current_org_id()'
  ' and (app.es_control()'
  '      or (app.current_rol() = ''super_intendente''::rol_usuario'
  '          and app.usuario_en_alcance(supervisor_id)'
  '          and app.usuario_en_alcance(residente_id)))');

create policy residente_obra_select on residente_obra
  for select using (
    org_id = app.current_org_id()
    and (app.es_config() or app.usuario_en_alcance(residente_id))
  );

create policy residente_obra_insert on residente_obra
  for insert with check (
    org_id = app.current_org_id()
    and app.puede_repartir_obra(residente_id, obra_id)
  );

create policy residente_obra_update on residente_obra
  for update
  using      (org_id = app.current_org_id() and app.puede_repartir_obra(residente_id, obra_id))
  with check (org_id = app.current_org_id() and app.puede_repartir_obra(residente_id, obra_id));

-- El DELETE NO exige que la obra siga siendo visible, y no es un olvido:
-- reasignar una obra del residente A al B es "inserta B, borra A", y entre las
-- dos sentencias la obra puede dejar de ser visible para quien reasigna si A
-- era su único vínculo. Exigirlo aquí volvería imposible la reasignación
-- —justo la operación que el usuario pidió que fuera fácil— sin cerrar nada:
-- quitar alcance nunca es una escalada.
create policy residente_obra_delete on residente_obra
  for delete using (
    org_id = app.current_org_id()
    and (app.es_control() or app.usuario_en_alcance(residente_id))
  );

-- ------------------------------------------------------------
-- 6 · El alta de obra se acota a Control
--
-- La 0012 la dejaba en `es_config()` acotado por `cluster_en_alcance`. Ahora
-- que Control ve toda la organización, ese predicado ya no acota nada para él,
-- y para el SI dejaría el mismo agujero de la 0016 al revés: crear una obra en
-- un cluster donde no tiene gente y no volver a verla.
--
-- Se cierra a Control, que además es lo que el router ya exigía desde la Fase 1
-- (`CREADOR_DE_OBRA = exigir_rol(Rol.CONTROL_OBRA)` en `api/v1/obras.py`): la
-- base deja de ser más ancha que la puerta.
--
-- El UPDATE conserva `es_config()`: un Super intendente sí edita y cierra las
-- obras de su gente, y el `using` ya lo acota a las que ve.
-- ------------------------------------------------------------
drop policy obra_insert on obra;

create policy obra_insert on obra
  for insert
  with check (
    org_id = app.current_org_id()
    and app.es_control()
  );

-- ------------------------------------------------------------
-- 7 · Lo que se queda, con su etiqueta puesta
-- ------------------------------------------------------------
comment on table control_proyecto is
  'INERTE PARA EL ALCANCE desde la 0042: control_obra ve toda la organización, así que este puente ya no acota nada. Se conserva —con sus datos, sus políticas y el trigger de autoasignación de la 0016— como registro de qué proyectos abrió o atiende cada Control, y para que la 0042 sea reversible.';

comment on table supervisor_cluster is
  'YA NO ALIMENTA RLS desde la 0042: el alcance del supervisor lo da supervisor_residente ("el alcance sigue a la gente"). Se conserva como dato territorial —qué manzanas recorre— y fue el origen del relleno de supervisor_residente.';

comment on column obra.residente_id is
  'Residente PRINCIPAL de la obra. Desde la 0042 ya no es la frontera de alcance —esa es residente_obra, que es M2M— sino una etiqueta que se mantiene en sincronía con el puente por trigger, para el código que sigue leyendo la columna (repos, notificaciones, reglas de cierre, sync rules).';

-- ------------------------------------------------------------
-- 8 · Reinicio de organización
--
-- La 0036 borra tabla por tabla con una lista literal, y su prueba de
-- integración recorre `information_schema` para reventar el día que alguien
-- agregue una tabla con `org_id` y se le olvide meterla. Estas son esas tres.
-- Van en el tier 2, junto a `supervisor_cluster`: cuelgan de `usuario` y de
-- `obra`, así que se borran antes que `cluster`/`proyecto` y no arrastran nada.
-- ------------------------------------------------------------
create or replace function app.reiniciar_organizacion()
returns jsonb
language plpgsql
security definer
set search_path = public, app, pg_temp
as $$
declare
  v_org      uuid := app.current_org_id();
  v_tabla    text;
  v_borradas bigint;
  v_resumen  jsonb := '{}'::jsonb;
  v_tablas   text[] := array[
    -- tier 5: hojas sin nada propio que las referencie
    'registro_avance', 'estimacion_concepto', 'solicitud_cierre', 'revision_fisica',
    -- tier 4
    'incidencia_evento', 'cierre_obra_participacion', 'evaluacion_respuesta',
    'periodo_bloqueado', 'actividad',
    -- tier 3
    'salida_almacen', 'incidencia', 'cierre_obra', 'evaluacion', 'expediente_doc',
    'partida_presupuesto', 'programa_base_item', 'cuadrilla_integrante',
    'explosion', 'grupo_funcional_insumo', 'estimacion', 'programa_obra',
    -- tier 2
    'presupuesto', 'programa_base', 'cuadrilla_version', 'cpu', 'insumo',
    'residente_obra', 'obra', 'supervisor_cluster', 'supervisor_residente',
    'superintendente_usuario', 'prototipo_nodo',
    -- tier 1
    'cluster', 'prototipo', 'control_proyecto', 'contratista_frente',
    'cuadrilla', 'concepto', 'etapa_constructiva', 'grupo_funcional',
    'pendiente', 'carga_snapshot',
    -- tier 0: independientes + las 17 auditadas por bitacora (sin bitacora)
    'carga_datos', 'motivo_almacen', 'criterio_evaluacion', 'contratista',
    'unidad', 'nivel', 'frente', 'proyecto', 'familia', 'configuracion',
    'ancla_semana', 'mapeo', 'proceso', 'evidencia', 'notificacion',
    'dispositivo_push', 'idempotencia', 'calendario',
    -- absoluto al final: las 17 de arriba escriben aquí al borrarse
    'bitacora'
  ];
begin
  if v_org is null then
    raise exception 'Sin organización en el contexto de sesión.';
  end if;
  if app.current_rol() <> 'control_obra' then
    raise exception 'Solo Control de obra puede reiniciar la organización.'
      using errcode = '42501';
  end if;

  foreach v_tabla in array v_tablas loop
    execute format('delete from public.%I where org_id = $1', v_tabla)
      using v_org;
    get diagnostics v_borradas = row_count;
    if v_borradas > 0 then
      v_resumen := v_resumen || jsonb_build_object(v_tabla, v_borradas);
    end if;
  end loop;

  return v_resumen;
end;
$$;
