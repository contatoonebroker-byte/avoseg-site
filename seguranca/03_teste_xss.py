"""Teste de regressão de XSS do painel (sistema.html), sem internet e sem banco.

Carrega o painel com um Supabase FALSO cujos dados têm códigos maliciosos em todos os campos,
visita todas as páginas e confirma que NENHUM script é executado.
Requer:  pip install playwright && playwright install chromium
Uso:     python3 seguranca/03_teste_xss.py
"""
import sys, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent.parent

PAY = '"><img src=x onerror="window.__xss=(window.__xss||0)+1">'
PAY_ID = "x');window.__xss=(window.__xss||0)+1;//"
DATA = {
 "leads": [{"id": PAY_ID, "name": PAY, "tel": PAY, "email": PAY, "product": PAY, "partner_name": PAY, "status": PAY, "obs": PAY, "created_at": "2026-09-01T10:00:00Z"},
           {"id": "l2", "name": "Ana", "tel": "1", "product": "Auto", "partner_name": "P1", "status": "Fechado", "created_at": "2026-09-01T10:00:00Z"}],
 "partners": [{"id": PAY_ID, "name": PAY, "type": PAY, "contact": PAY, "tel": PAY, "email": PAY, "commission": PAY, "pass": "x", "bank": PAY, "pix": PAY, "agency": PAY, "account": PAY}],
 "commissions": [{"id": PAY_ID, "partner_name": PAY, "lead_id": "l2", "lead_name": PAY, "product": PAY, "value": 100, "type": PAY, "due_date": PAY, "status": PAY, "obs": PAY, "receipt_url": "javascript:window.__xss=(window.__xss||0)+1", "created_at": "2026-09-01T10:00:00Z"}],
 "client_referrals": [{"id": PAY_ID, "referrer_cpf": PAY, "referrer_name": PAY, "referrer_phone": PAY, "client_name": PAY, "client_phone": PAY, "client_email": PAY, "product": PAY, "obs": PAY, "status": PAY, "created_at": "2026-09-01T10:00:00Z"}],
 "lead_history": [{"id": "h1", "lead_id": PAY_ID, "type": PAY, "text": PAY, "created_at": "2026-09-01T10:00:00Z"}],
 "admin_users": [{"id": "u1"}],
}
STUB = """
window.__DATA = %s;
function Q(t){ var q={_t:t};
  ['select','order','eq','ilike','insert','update','delete','limit','in'].forEach(function(m){ q[m]=function(){return q;}; });
  q.maybeSingle=q.single=function(){ return Promise.resolve({data:(window.__DATA[t]||[])[0]||null,error:null}); };
  q.then=function(res,rej){ return Promise.resolve({data:window.__DATA[t]||[],error:null}).then(res,rej); };
  return q; }
window.supabase={createClient:function(){return {
  auth:{signInWithPassword:async function(){return {data:{user:{id:'u1'}},error:null};},signOut:async function(){}},
  from:Q, storage:{from:function(){return {upload:async function(){return {error:null};},getPublicUrl:function(){return {data:{publicUrl:'https://x/y.pdf'}};}};}}};}};
window.XLSX={utils:{},write:function(){}};
""" % json.dumps(DATA)

def run(path):
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": __import__("os").environ["CHROMIUM"]} if __import__("os").environ.get("CHROMIUM") else {}))
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        pg.on("dialog", lambda d: d.dismiss())
        def route(r):
            u = r.request.url
            if "supabase-js" in u or "xlsx" in u:
                r.fulfill(status=200, content_type="application/javascript", body=STUB)
            elif u.startswith("file:"):
                r.continue_()
            else:
                r.abort()
        pg.route("**/*", route)
        import re, os, shutil
        tmp = str(ROOT / ".tmp_test.html")
        open(tmp, "w").write(re.sub(r' integrity="[^"]*"', '', open(path).read()))
        pg.goto("file://" + tmp); time.sleep(0.5)
        pg.evaluate("loginType='admin'")
        pg.fill("#admin-email", "a@a.com"); pg.fill("#admin-pass", "x")
        pg.evaluate("doLogin()"); time.sleep(0.8)
        ids = pg.evaluate("adminNav.filter(function(x){return x.id;}).map(function(x){return x.id;})")
        for i in ids:
            pg.evaluate("navigate(%s)" % json.dumps(i)); time.sleep(0.4)
        for fn in ["openChangePassModal()", "openDetail(%s)" % json.dumps(PAY_ID), "openModal('modal-commission')"]:
            try: pg.evaluate(fn); time.sleep(0.4)
            except Exception as e: errs.append("evalfail " + fn[:20])
        # cliques em elementos gerados (onclick, links)
        for sel in ["a.receipt-link", ".btn-danger"]:
            try:
                for el in pg.query_selector_all(sel)[:2]:
                    el.click(timeout=800)
            except Exception: pass
        time.sleep(0.5)
        # visão do parceiro
        pg.evaluate("S.partnerName=%s; startApp('partner',%s,%s)" % (json.dumps(PAY), json.dumps(PAY), json.dumps(PAY))); time.sleep(0.8)
        n = pg.evaluate("window.__xss||0")
        html_imgs = pg.evaluate("document.querySelectorAll('img[src=\"x\"]').length")
        b.close()
        os.remove(tmp)
        return n, html_imgs, errs, len(ids)

n, imgs, errs, pages = run(str(ROOT / "sistema.html"))
print(f"páginas visitadas: {pages} | scripts executados (XSS): {n} | <img> injetadas: {imgs} | erros JS: {errs[:3]}")
raise SystemExit(0 if n == 0 and imgs == 0 else 1)
