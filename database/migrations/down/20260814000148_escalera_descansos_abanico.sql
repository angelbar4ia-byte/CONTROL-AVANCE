-- Revierte la 0148: desaparecen los descansos propios y los escalones de abanico; las escaleras vuelven a su descanso implícito (la propuesta de EJ-820 no se toca).
drop table if exists escalera_abanico;
drop table if exists escalera_descanso;
