-- ============================================================================
-- BLOQUEIO IMEDIATO (fase 1): liga o RLS e deixa o acesso mínimo para o site funcionar.
--
-- Depois de rodar:
--   * Painel de admin (login por e-mail e senha)  -> continua funcionando
--   * Formulário público "Indique e Ganhe"        -> continua funcionando (só envia, não lê)
--   * Visitante anônimo                           -> NÃO lê nem altera mais nada
--   * Portal do PARCEIRO (login por nome e senha) -> fica INDISPONÍVEL até migrarmos para o
--     Supabase Auth (fase 2). É o preço de fechar o vazamento.
--
-- Tudo roda numa transação: se algo falhar, nada é aplicado.
-- ============================================================================
begin;

-- 1) Função que diz se quem chama é administrador (só existe em admin_users)
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.admin_users where id = auth.uid());
$$;
revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to authenticated;

-- 2) Liga o RLS em todas as tabelas (sem política = ninguém acessa)
alter table public.admin_users      enable row level security;
alter table public.partners         enable row level security;
alter table public.leads            enable row level security;
alter table public.lead_history     enable row level security;
alter table public.commissions      enable row level security;
alter table public.client_referrals enable row level security;

-- 3) Administrador: acesso total (somente quem está em admin_users)
drop policy if exists "admin total" on public.admin_users;
drop policy if exists "admin total" on public.partners;
drop policy if exists "admin total" on public.leads;
drop policy if exists "admin total" on public.lead_history;
drop policy if exists "admin total" on public.commissions;
drop policy if exists "admin total" on public.client_referrals;

create policy "admin total" on public.admin_users      for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admin total" on public.partners         for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admin total" on public.leads            for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admin total" on public.lead_history     for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admin total" on public.commissions      for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admin total" on public.client_referrals for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- 4) Formulário público: só INSERIR indicação, sempre como "Novo" e com tamanhos limitados
drop policy if exists "publico envia indicacao" on public.client_referrals;
create policy "publico envia indicacao" on public.client_referrals
  for insert to anon
  with check (
    status = 'Novo'
    and length(referrer_cpf::text)   between 11 and 14
    and length(referrer_name::text)  between 2 and 150
    and length(referrer_phone::text) between 8 and 30
    and length(client_name::text)    between 2 and 150
    and length(client_phone::text)   between 8 and 30
    and length(coalesce(client_email::text, '')) <= 200
    and length(coalesce(obs::text, ''))          <= 1000
  );

-- 5) Defesa em profundidade: o papel anônimo perde o acesso direto às tabelas
revoke all on public.admin_users, public.partners, public.leads,
              public.lead_history, public.commissions, public.client_referrals from anon;
grant insert on public.client_referrals to anon;

commit;

-- ============================================================================
-- ROLLBACK DE EMERGÊNCIA (REABRE O VAZAMENTO! só se o painel de admin quebrar e você não puder esperar):
--   alter table public.leads disable row level security;   -- e assim por diante, tabela a tabela
-- Prefira me chamar para corrigir a política.
-- ============================================================================
