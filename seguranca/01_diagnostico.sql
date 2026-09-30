-- ============================================================================
-- DIAGNÓSTICO DE SEGURANÇA DO SUPABASE  (somente leitura: não altera nada)
-- Como usar: Supabase > SQL Editor > New query > cole e rode CADA bloco (ou tudo).
-- Depois copie os RESULTADOS (estrutura e contagens; não há dados de clientes aqui)
-- e cole no chat. NÃO cole chaves, senhas nem linhas de dados.
-- ============================================================================

-- 1) RLS está ligado em cada tabela?  (rls_ativo = false  =>  tabela ABERTA)
select c.relname as tabela, c.relrowsecurity as rls_ativo, c.relforcerowsecurity as rls_forcado
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by 1;

-- 2) Políticas existentes (quem pode ler/gravar o quê)
select tablename as tabela, policyname as politica, roles, cmd as operacao,
       qual as condicao_using, with_check as condicao_check
from pg_policies
where schemaname = 'public'
order by tablename, cmd, policyname;

-- 3) Permissões diretas dos papéis públicos (anon = qualquer visitante do site)
select table_name as tabela, grantee as papel,
       string_agg(privilege_type, ', ' order by privilege_type) as permissoes
from information_schema.role_table_grants
where table_schema = 'public' and grantee in ('anon', 'authenticated')
group by 1, 2
order by 1, 2;

-- 4) Colunas de cada tabela (estrutura, sem dados)
select table_name as tabela, column_name as coluna, data_type as tipo, is_nullable as aceita_nulo
from information_schema.columns
where table_schema = 'public'
order by table_name, ordinal_position;

-- 5) Armazenamento de arquivos: o bucket dos comprovantes é público?
select id, name, public as publico, file_size_limit, allowed_mime_types
from storage.buckets;

-- 6) Políticas do armazenamento
select policyname as politica, roles, cmd as operacao,
       qual as condicao_using, with_check as condicao_check
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
order by cmd, policyname;

-- 7) Contagens (sem revelar dados)
select
  (select count(*) from public.admin_users) as admins,
  (select count(*) from auth.users)         as usuarios_auth,
  (select count(*) from public.partners)    as parceiros,
  (select count(*) from public.partners where pass is not null and pass <> '') as parceiros_com_senha_na_tabela,
  (select count(*) from public.partners where pass ~ '^\$2[aby]\$') as senhas_com_hash_bcrypt;

-- 8) Funções (RPC) expostas pela API
select routine_name as funcao, security_type
from information_schema.routines
where routine_schema = 'public'
order by 1;

-- ============================================================================
-- CONFERIR NO PAINEL (não dá para ver por SQL):
--  * Authentication > Providers > Email: "Allow new users to sign up" deve estar DESLIGADO
--    (senão qualquer pessoa cria uma conta e vira "authenticated").
--  * Authentication > Attack Protection: proteção contra abuso / CAPTCHA.
--  * Settings > API: a chave 'service_role' NUNCA pode ter sido usada em site ou repositório.
-- ============================================================================
