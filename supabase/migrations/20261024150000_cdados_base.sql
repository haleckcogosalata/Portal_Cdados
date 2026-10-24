-- CDADOS: esquema base.
--
-- O projeto Supabase é compartilhado com outros sistemas (plano free), então TUDO que este
-- sistema cria leva o prefixo `cdados_` (tabelas, funções, views, índices, políticas).
-- Identificadores ficam em minúsculas de propósito: `CDADOS_x` entre aspas obrigaria a citar
-- o nome em todo SQL e URL; sem aspas o Postgres já converte para minúsculas.
--
-- Segurança: RLS ligado em todas as tabelas; só quem está em `cdados_admins` acessa.
-- O papel `anon` não recebe nenhum privilégio. Os robôs usam a service_role.
--
-- Primeiro acesso: crie o usuário em Authentication e depois execute, no SQL Editor:
--   insert into public.cdados_admins (user_id) values ('<uuid do usuário>');

-- ---------------------------------------------------------------------------
-- Acesso
-- ---------------------------------------------------------------------------

create table public.cdados_admins (
  user_id uuid primary key references auth.users (id) on delete cascade,
  criado_em timestamptz not null default now()
);

create function public.cdados_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (select 1 from public.cdados_admins where user_id = auth.uid());
$$;

-- ---------------------------------------------------------------------------
-- Cadastro: turmas, disciplinas, docentes
-- ---------------------------------------------------------------------------

-- id = rótulo usado no nome dos cursos do Moodle: '2025_2', '2026_1_turma_7', '2026_2_turma_9'.
create table public.cdados_turmas (
  id text primary key,
  periodo text not null,            -- '2025_2'
  numero integer,                   -- turma 5, 6, 7...
  nome text,
  criado_em timestamptz not null default now()
);

create table public.cdados_disciplinas (
  codigo text primary key,          -- 'AEBC1', 'LPRC2'
  nome text not null,
  nome_curto text,
  carga_horaria integer,
  ordem integer not null default 0,
  ativa boolean not null default true
);

-- Nomes equivalentes de uma mesma disciplina (substitui `Mapa_disciplinas`).
-- O robô casa o nome do curso do Moodle contra estes nomes, sem acento nem caixa.
create table public.cdados_disciplina_nomes (
  nome text primary key,
  codigo text not null references public.cdados_disciplinas (codigo) on update cascade
);

create table public.cdados_docentes (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  email text,
  papel text not null check (papel in ('docente', 'tutor')),
  telegram_chat_id text,            -- reservado para o módulo de notificações
  unique (nome, papel)
);

-- Oferta: uma disciplina em uma turma.
create table public.cdados_ofertas (
  turma_id text not null references public.cdados_turmas (id) on update cascade,
  disciplina_codigo text not null references public.cdados_disciplinas (codigo) on update cascade,
  moodle_id_curso integer,
  moodle_url text,
  grupo_whatsapp text,
  primary key (turma_id, disciplina_codigo)
);

create table public.cdados_oferta_docentes (
  turma_id text not null,
  disciplina_codigo text not null,
  docente_id uuid not null references public.cdados_docentes (id) on delete cascade,
  ordem integer not null default 1,
  primary key (turma_id, disciplina_codigo, docente_id),
  foreign key (turma_id, disciplina_codigo)
    references public.cdados_ofertas (turma_id, disciplina_codigo) on delete cascade
);

-- ---------------------------------------------------------------------------
-- Cronograma (substitui as grades por turma e `Lista_Eventos_DB`)
-- ---------------------------------------------------------------------------
-- AS aula ao vivo, AA aula offline, AV avaliação, REC segunda chamada/recuperação,
-- NP nota parcial no acadêmico, NF nota final no acadêmico, RC recesso, FE férias/feriado.

create table public.cdados_cronograma_eventos (
  id uuid primary key default gen_random_uuid(),
  turma_id text not null references public.cdados_turmas (id) on update cascade,
  disciplina_codigo text references public.cdados_disciplinas (codigo) on update cascade,
  titulo text,                      -- para eventos sem disciplina (ex.: Aula inaugural)
  tipo text not null check (tipo in ('AS', 'AA', 'AV', 'REC', 'NP', 'NF', 'RC', 'FE')),
  data_inicio date not null,
  data_fim date not null,
  observacao text,
  check (data_fim >= data_inicio),
  check (disciplina_codigo is not null or titulo is not null)
);

create index cdados_cronograma_eventos_turma_disc_idx
  on public.cdados_cronograma_eventos (turma_id, disciplina_codigo, tipo);

-- Janelas por oferta, no mesmo formato de MINIFS/MAXIFS da matriz (AV e REC).
create view public.cdados_v_janelas
with (security_invoker = true) as
select
  turma_id,
  disciplina_codigo,
  min(data_inicio) filter (where tipo not in ('RC', 'FE')) as inicio_disciplina,
  min(data_inicio) filter (where tipo = 'AV') as av_inicio,
  max(data_fim) filter (where tipo = 'AV') as av_fim,
  min(data_inicio) filter (where tipo = 'REC') as rec_inicio,
  max(data_fim) filter (where tipo = 'REC') as rec_fim
from public.cdados_cronograma_eventos
where disciplina_codigo is not null
group by turma_id, disciplina_codigo;

-- ---------------------------------------------------------------------------
-- Alunos
-- ---------------------------------------------------------------------------

-- nome = nome no sistema acadêmico (canônico). nome_chave = nome sem acento, em caixa alta,
-- calculado pela aplicação (packages/core: normalizeName).
create table public.cdados_alunos (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  nome_chave text not null unique,
  email text,
  whatsapp text,
  cidade text,
  uf text,
  formacao text,
  tipo text not null default 'Comum' check (tipo in ('Comum', 'Servidor')),
  criado_em timestamptz not null default now()
);

-- Substitui `ajuste_nomes` (Supabase) e `Ajuste Nomes Acadêmico` (planilha).
create table public.cdados_aluno_alias (
  alias_chave text primary key,     -- nome como vem do Moodle/CSV, normalizado
  alias text not null,
  aluno_id uuid not null references public.cdados_alunos (id) on delete cascade
);

create index cdados_aluno_alias_aluno_idx on public.cdados_aluno_alias (aluno_id);

create table public.cdados_inscricoes (
  aluno_id uuid not null references public.cdados_alunos (id) on delete cascade,
  turma_id text not null references public.cdados_turmas (id) on update cascade,
  situacao text,                    -- 'Desistente', ou nota livre da coluna SITUAÇÃO
  primary key (aluno_id, turma_id)
);

create table public.cdados_anotacoes (
  id uuid primary key default gen_random_uuid(),
  aluno_id uuid not null references public.cdados_alunos (id) on delete cascade,
  turma_id text references public.cdados_turmas (id) on update cascade,
  texto text not null,
  criado_em timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Dados extraídos pelos robôs
-- ---------------------------------------------------------------------------

create table public.cdados_moodle_cursos (
  id_curso integer primary key,
  nome text not null,
  turma_id text references public.cdados_turmas (id) on update cascade,
  disciplina_codigo text references public.cdados_disciplinas (codigo) on update cascade,
  recuperacao boolean not null default false,   -- nome contém "- RECUPERAÇÃO"
  nota_maxima numeric,                           -- escala real do curso, quando o robô a obtém
  extraido_em timestamptz not null default now()
);

create table public.cdados_moodle_notas (
  id_curso integer not null references public.cdados_moodle_cursos (id_curso) on delete cascade,
  email text not null,
  nome_moodle text not null,
  aluno_id uuid references public.cdados_alunos (id) on delete set null,
  nota_raw text,                                 -- como veio: '-', '9,67', 'Erro'
  nota_0_10 numeric,                             -- calculada por packages/core
  extraido_em timestamptz not null default now(),
  primary key (id_curso, email)
);

create index cdados_moodle_notas_aluno_idx on public.cdados_moodle_notas (aluno_id);

create table public.cdados_moodle_participantes (
  id_curso integer not null references public.cdados_moodle_cursos (id_curso) on delete cascade,
  email text not null,
  nome_moodle text not null,
  aluno_id uuid references public.cdados_alunos (id) on delete set null,
  papel text,                                    -- 'Estudante', 'Professor'...
  grupos text,
  ultimo_acesso_raw text,                        -- 'Nunca', '3 dias 4 horas'
  ultimo_acesso_seg bigint,                      -- null quando nunca acessou
  situacao text,
  extraido_em timestamptz not null default now(),
  primary key (id_curso, email)
);

create index cdados_moodle_participantes_aluno_idx on public.cdados_moodle_participantes (aluno_id);

create table public.cdados_academico_notas (
  id uuid primary key default gen_random_uuid(),
  aluno_id uuid references public.cdados_alunos (id) on delete set null,
  nome_csv text not null,                        -- nome usado na busca
  nome_sistema text not null,                    -- nome encontrado no SIORG
  disciplina_codigo text,                        -- código do SIORG, ex.: 'AEBC1'
  disciplina_nome text,
  turma_academica text,                          -- 'CDADOS4'
  media_final numeric,
  pendente boolean not null default false,       -- '*' = lançamento pendente
  situacao text,
  observacoes text,
  extraido_em timestamptz not null default now(),
  unique (nome_sistema, disciplina_codigo, turma_academica)
);

create index cdados_academico_notas_aluno_idx on public.cdados_academico_notas (aluno_id);

-- Erros de busca do robô acadêmico ficam aqui, nunca em `cdados_academico_notas`.
create table public.cdados_academico_falhas (
  id uuid primary key default gen_random_uuid(),
  nome_csv text not null,
  motivo text not null,
  job_id uuid,
  criado_em timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Regras e execuções
-- ---------------------------------------------------------------------------

create table public.cdados_regras (
  id uuid primary key default gen_random_uuid(),
  versao integer not null,
  config jsonb not null,            -- { regrasLogicas, regrasExclusao } (packages/core RuleSet)
  ativa boolean not null default false,
  criado_em timestamptz not null default now(),
  criado_por uuid references auth.users (id)
);

-- No máximo uma versão ativa.
create unique index cdados_regras_ativa_idx on public.cdados_regras (ativa) where ativa;

create table public.cdados_jobs (
  id uuid primary key default gen_random_uuid(),
  tipo text not null check (tipo in ('moodle', 'academico', 'pipeline')),
  params jsonb not null default '{}',
  status text not null default 'pendente'
    check (status in ('pendente', 'executando', 'concluido', 'erro', 'cancelado')),
  progresso numeric not null default 0 check (progresso between 0 and 1),
  erro text,
  criado_em timestamptz not null default now(),
  iniciado_em timestamptz,
  finalizado_em timestamptz
);

create table public.cdados_job_logs (
  id bigint generated always as identity primary key,
  job_id uuid not null references public.cdados_jobs (id) on delete cascade,
  nivel text not null default 'info' check (nivel in ('info', 'aviso', 'erro')),
  mensagem text not null,
  criado_em timestamptz not null default now()
);

create index cdados_job_logs_job_idx on public.cdados_job_logs (job_id, id);

alter table public.cdados_academico_falhas
  add constraint cdados_academico_falhas_job_fk
  foreign key (job_id) references public.cdados_jobs (id) on delete set null;

-- ---------------------------------------------------------------------------
-- RLS: fechado por padrão, aberto só a administradores
-- ---------------------------------------------------------------------------

do $$
declare
  t text;
begin
  for t in
    select tablename from pg_tables
    where schemaname = 'public' and tablename like 'cdados\_%' escape '\'
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon', t);
    if t = 'cdados_admins' then
      -- cada usuário só enxerga a própria linha; ninguém grava pela API
      execute format(
        'create policy %I on public.%I for select to authenticated using (user_id = auth.uid())',
        t || '_self', t
      );
    else
      execute format(
        'create policy %I on public.%I for all to authenticated using (public.cdados_is_admin()) with check (public.cdados_is_admin())',
        t || '_admin', t
      );
    end if;
  end loop;
end $$;

revoke all on public.cdados_v_janelas from anon;
revoke all on function public.cdados_is_admin() from public, anon;
grant execute on function public.cdados_is_admin() to authenticated, service_role;

-- Progresso dos robôs em tempo real na interface.
alter publication supabase_realtime add table public.cdados_jobs, public.cdados_job_logs;
