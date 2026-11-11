delete from vano where tipo = 'castillo';
delete from vano_version where tipo = 'castillo';
alter table vano_version drop constraint if exists ck_vano_version_tipo;
alter table vano_version
  add constraint ck_vano_version_tipo check (tipo in ('puerta', 'ventana', 'cancel', 'arco', 'paso'));
alter table vano drop constraint if exists ck_vano_tipo;
alter table vano
  add constraint ck_vano_tipo check (tipo in ('puerta', 'ventana', 'cancel', 'arco', 'paso'));
