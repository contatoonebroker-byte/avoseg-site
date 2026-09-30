"""Teste NÃO INVASIVO: o que um visitante anônimo (só com a chave pública do site) consegue LER?

Só faz requisições HEAD com contagem (não baixa nenhuma linha) e não grava nada.
Uso (no Terminal, na pasta do projeto):
    SUPABASE_URL=https://SEU-PROJETO.supabase.co SUPABASE_ANON_KEY=CHAVE_ANON \
        python3 seguranca/02_testar_exposicao.py
"""
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_ANON_KEY", "")
TABELAS = ["partners", "leads", "commissions", "client_referrals", "lead_history", "admin_users"]

if not URL or not KEY:
    sys.exit("Defina SUPABASE_URL e SUPABASE_ANON_KEY (veja o topo do arquivo).")

print(f"Testando leitura anônima em {URL}\n")
expostas = 0
for t in TABELAS:
    req = urllib.request.Request(
        f"{URL}/rest/v1/{t}?select=id", method="HEAD",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Prefer": "count=exact"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            total = (r.headers.get("Content-Range") or "*/?").split("/")[-1]
            if total in ("0", "?"):
                print(f"  {t:18s} acesso permitido, mas 0 linhas visíveis (ok)")
            else:
                print(f"  {t:18s} ANÔNIMO CONSEGUE LER ({total} linhas)  <-- EXPOSTA")
                expostas += 1
    except urllib.error.HTTPError as e:
        print(f"  {t:18s} bloqueada (HTTP {e.code})  ok")
    except Exception as e:
        print(f"  {t:18s} erro de rede: {e}")

print(f"\n{expostas} tabela(s) legível(is) por qualquer visitante." +
      ("  ATENÇÃO: corrija o RLS antes de conectar o Jarvis." if expostas else ""))
