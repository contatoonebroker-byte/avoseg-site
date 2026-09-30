# Plano: JARVIS como assistente pessoal + Avoseg + Avogroup

## 1. O que já existe

**Jarvis (pasta `jarvis/`)**: voz (hotword, Whisper local, Claude, ElevenLabs/voz do Mac), abertura com música,
modo conversa ("Jarvis, ..."), tela HUD com widgets (clima, monitor, Spotify, timers, agenda/e-mail prontos).

**Sistemas Avoseg (raiz do repositório)**, ambos HTML estático + Supabase:
- `index.html`: "Avoseg Indica": clientes indicam e ganham R$ 100 (grava em `client_referrals`).
- `sistema.html`: "Avoseg Parceiros": painel de admin e de parceiros.
  Tabelas: `leads`, `lead_history`, `partners`, `commissions`, `client_referrals`, `admin_users`;
  bucket de arquivos: `comprovantes`.

**Avogroup**: não há nada dele neste repositório (é o único acessível a esta sessão). Precisamos mapear.

## 2. Alerta de segurança (fazer ANTES de conectar o Jarvis)

Pelo código (não testei o banco em produção, só li o HTML):

1. O repositório é **público** e o `sistema.html` traz a URL do Supabase e a chave `anon`.
   A chave `anon` é feita para ser pública, mas **só é segura se o RLS (Row Level Security) estiver bem configurado**.
2. O login do parceiro faz `partners.select('*').ilike('name', nome).eq('pass', senha)` **no navegador**.
   Isso só funciona se a chave `anon` puder **ler a tabela `partners` inteira**, que tem senha (`pass`, aparentemente
   em texto puro), CPF, banco, agência, conta e PIX. Se for isso, qualquer pessoa com a chave pública consegue baixar
   os dados de todos os parceiros.
3. Os dados são de terceiros (LGPD): CPF, dados bancários, telefones de indicados.

**Correção recomendada (Fase 0):** RLS restritivo por tabela; login de parceiro via Supabase Auth (senha com hash, não
em coluna `pass`); `partners` sem leitura pública; consultas do parceiro só às próprias linhas; comprovantes com URL
assinada. O Jarvis nunca usa a chave `anon`: usa uma credencial própria e restrita (ver §5).

## 3. Arquitetura alvo

```
Voz / HUD / Tablet / (depois) Telegram-WhatsApp
                    │
              JARVIS NÚCLEO (Claude + tool use)
   ┌────────────────┼─────────────────┬──────────────────┐
 SECOND BRAIN     SKILLS          CONECTORES        PROATIVIDADE
 (memória)     (habilidades)   (sistemas externos)  (agenda de tarefas)
```

### 3.1 Second Brain
- Pasta de notas em **Markdown** (compatível com Obsidian) em `~/JarvisBrain/`, com backup/sincronização em
  repositório **privado** ou iCloud/Drive.
- Estrutura (método PARA):
  `00-Inbox/ · 10-Pessoal/ · 20-Avoseg/ · 30-Avogroup/ · 40-Projetos/ · 50-Pessoas/ · 60-Reuniões/ · 70-Diário/ · 80-Decisões/ · 90-Arquivo/`
- `perfil.md`: quem você é, preferências, rotina, como quer ser tratado. Sempre carregado no prompt do Jarvis.
- Busca: começa com **SQLite FTS5** (palavras-chave, rápido, local); depois **embeddings locais** para busca por significado.
- Habilidades de memória: "anote que...", "lembra que...", "o que decidi sobre X?", "o que combinei com Fulano?",
  "resumo da semana", captura de ideias por voz direto no Inbox, resumo automático de cada conversa no Diário.
- Cada workspace (Pessoal, Avoseg, Avogroup) tem sua pasta, então nada se mistura.

### 3.2 Skills (habilidades)
Cada skill é uma pasta `skills/<nome>/` com um manifesto (`skill.yaml`) e as ferramentas em Python:

```yaml
nome: leads_avoseg
workspace: avoseg
descricao: Consulta e atualiza leads do funil da Avoseg
ferramentas: [listar_leads, mudar_status_lead, registrar_historico]
permissoes:
  leitura: livre
  escrita: confirmar_por_voz
  financeiro: confirmar_com_pin
```
O Jarvis carrega as skills do workspace ativo ("modo Avoseg", "modo pessoal"). Criar uma skill nova = uma pasta nova.

Skills pessoais (exemplos): agenda, e-mail, tarefas, lembretes, finanças pessoais, saúde/hábitos, viagens, casa, estudos, música.

Skills de empresa (exemplos, a confirmar com você): funil de leads, follow-up (rascunhar mensagens de WhatsApp),
comissões e pagamentos de parceiros, relatórios diários e semanais, marketing (legendas, posts, roteiros),
atendimento (rascunhos de respostas), financeiro (contas a pagar/receber), reuniões (ata e tarefas), contratos.

### 3.3 Conectores
| Sistema | Como | Fase |
|---|---|---|
| Google Agenda, Gmail, Tasks, Drive | API do Google (OAuth) | 2 |
| Spotify | API do Spotify | 2 |
| **Avoseg (Supabase)** | Cliente Python com credencial restrita + log de auditoria | 3 |
| Avogroup | A definir (ver §6) | 4 |
| WhatsApp | API oficial ou provedor; envio só com confirmação | 5 |
| Mac (Lembretes, Notas, Arquivos) | AppleScript / Atalhos | 2 |

Cada conector é um arquivo em `jarvis/connectors/`, com a mesma interface, para adicionar sistemas sem mexer no núcleo.

### 3.4 Avoseg: o que o Jarvis passa a fazer
- **Perguntas:** "quantos leads novos hoje?", "quais comissões estão pendentes?", "como está o funil?", "quem mais indicou este mês?".
- **Ações (com confirmação por voz):** mudar status de lead, registrar histórico, cadastrar parceiro,
  marcar comissão como paga (esta pede também um PIN).
- **Alertas em tempo real** (Supabase Realtime): "Senhor, chegou uma nova indicação de Maria Silva", com voz e HUD.
- **HUD:** funil de leads, comissões a pagar, top parceiros, indicações do dia.
- **Briefing matinal:** agenda + e-mails importantes + leads novos + comissões a pagar + clima.

### 3.5 Proatividade
Agendador (launchd no Mac): briefing matinal, fechamento do dia, lembretes, monitoramento de novas indicações,
cobranças pendentes. Avisos por voz, HUD e notificação no celular (ntfy/Pushover).

## 4. Fases

| Fase | Entrega | Resultado |
|---|---|---|
| **0. Segurança e fundação** | Revisar RLS e login de parceiros; mover o Jarvis para repositório **privado**; segredos no Keychain; estrutura de skills e workspaces | Base segura para dados reais |
| **1. Second Brain v1** | Notas Markdown, busca FTS5, perfil, captura por voz, diário automático | "Anota isso", "o que decidi sobre X?" |
| **2. Google + Spotify + Mac** | Agenda, Gmail, Tasks, Drive, Spotify; briefing matinal; painéis do HUD | Assistente pessoal útil no dia a dia |
| **3. Avoseg** | Conector Supabase (leitura, depois escrita com confirmação), alertas em tempo real, widgets | Jarvis operando a Avoseg |
| **4. Avogroup** | Mapeamento dos sistemas e conectores | Jarvis operando o grupo |
| **5. Proatividade e canais** | Agendador, notificações, Telegram/WhatsApp, servidor 24 h (Mac mini ou VPS) | Funciona fora de casa e com o Mac fechado |
| **6. Skills avançadas** | Marketing, financeiro, atendimento, reuniões; agentes para tarefas longas; reconhecimento de voz do dono | Assistente completo |

## 5. Segurança, LGPD e controle

- **Credencial própria do Jarvis no Supabase** (usuário dedicado com política RLS mínima, ou papel restrito); a chave
  `service_role` nunca vai para o navegador nem para o repositório.
- **Confirmação por voz** para toda escrita; **PIN** para dinheiro (comissões) e dados sensíveis; modo "simulação" que só descreve o que faria.
- **Log de auditoria** (tabela `jarvis_audit`): quem/quando/o quê, para toda ação.
- **Minimização de dados:** CPF, PIX e conta mascarados antes de irem ao modelo; o Jarvis não precisa ver a senha de ninguém.
- Segredos no Keychain do macOS (biblioteca `keyring`), nunca em código.
- Cópias de segurança do Second Brain e do log.
- Dados de clientes e parceiros passam pela API da Anthropic: avaliar retenção zero (ZDR) e informar isso na política de privacidade.

## 6. Perguntas para decidir

1. **Avogroup:** quais empresas e sistemas o grupo tem? Onde ficam os dados (Supabase, planilhas, CRM, ERP, outro)?
   Existe repositório ou arquivos para eu ler?
2. **Avoseg:** qual é o negócio (tipo de seguro/serviço) e quais rotinas você quer automatizar primeiro?
3. **Segurança:** posso começar pela Fase 0 (auditar as regras de acesso do Supabase e propor as correções)?
   Preciso que você me passe o `schema` e as políticas RLS (exportadas do painel do Supabase), **sem chaves**.
4. **Second Brain:** você já usa Obsidian, Notion ou outra ferramenta de notas? Quer migrar o que já existe?
5. **Canais:** quer poder falar com o Jarvis pelo celular (Telegram ou WhatsApp) quando estiver fora?
6. **Servidor 24 h:** prefere manter no MacBook ou ter uma máquina/servidor sempre ligado para alertas?
