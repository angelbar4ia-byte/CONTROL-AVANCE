-- down · 0100 · WBS y Nivel ERP del nodo de prototipo
alter table prototipo_nodo drop column if exists nivel_erp;
alter table prototipo_nodo drop column if exists wbs;
