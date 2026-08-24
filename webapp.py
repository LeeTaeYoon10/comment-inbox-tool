# -*- coding: utf-8 -*-
"""
로컬 웹앱 UI — 실행하면 브라우저에 댓글 통합관리 화면이 열림.
백엔드는 로컬 파이썬(브라우저 자동화)이고, 프론트는 localhost 웹페이지.

python webapp.py   → http://localhost:8765 자동 오픈
"""
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import inbox_actions

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "inbox_comments.json")
ACCF = os.path.join(BASE, "inbox_accounts.json")
PORT = 8765


def load_accounts_file():
    if os.path.exists(ACCF):
        try:
            return json.load(open(ACCF, encoding="utf-8"))
        except Exception:
            pass
    return {"business_id": "", "accounts": []}


def approx_days(t):
    if not t:
        return 99999
    m = re.match(r"(\d+)(주|일|시간|분|초)", t)
    if m:
        n = int(m.group(1)); u = m.group(2)
        return {"주": n*7, "일": n, "시간": n/24, "분": n/1440, "초": 0}.get(u, n)
    m = re.match(r"(\d+)월\s*(\d+)일", t)
    if m:
        return 300 - (int(m.group(1))*30 + int(m.group(2)))
    return 99999


def parse_link(url):
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url.strip()).query)
    except Exception:
        return None, None
    biz = (q.get("business_id") or [None])[0]
    pid = (q.get("asset_id") or q.get("mailbox_id") or q.get("page_id") or [None])[0]
    return biz, pid


def get_rows():
    if not os.path.exists(DATA):
        return []
    posts = json.load(open(DATA, encoding="utf-8"))
    conf = load_accounts_file()
    pid_biz = {a["page_id"]: a.get("business_id") for a in conf["accounts"]}
    pid_of = {a["ig"]: a["page_id"] for a in conf["accounts"]}
    rows = []
    for post in posts:
        pid = post.get("page_id") or pid_of.get(post["account"])
        for c in post["comments"]:
            rows.append({
                "brand": post.get("brand", ""), "account": post["account"], "plat": post["platform"],
                "page_id": pid, "business_id": pid_biz.get(pid), "post": post["post_preview"],
                "author": c["author"], "text": c["text"], "likes": c.get("likes", ""),
                "time": c.get("time", ""),
            })
    rows.sort(key=lambda r: approx_days(r["time"]))
    return rows


def check_login():
    """로그인 브라우저(CDP 9222)가 살아있고 Business Suite에 로그인됐는지."""
    try:
        raw = urllib.request.urlopen("http://localhost:9222/json", timeout=2).read()
        tabs = json.loads(raw)
    except Exception:
        return {"browser": False, "logged_in": False}
    for t in tabs:
        u = t.get("url", "")
        if "business.facebook.com" in u and "login" not in u.lower():
            return {"browser": True, "logged_in": True}
    return {"browser": True, "logged_in": False}


COLLECT_STATE = {"running": False, "msg": ""}


def run_collect():
    COLLECT_STATE["running"] = True
    COLLECT_STATE["msg"] = "전 계정 수집 중..."
    try:
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        subprocess.run([sys.executable, os.path.join(BASE, "inbox_collect.py")],
                       cwd=BASE, env=env, timeout=900)
        COLLECT_STATE["msg"] = "수집 완료"
    except Exception as e:
        COLLECT_STATE["msg"] = f"수집 오류: {e}"
    finally:
        COLLECT_STATE["running"] = False


INDEX_HTML = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<title>댓글 통합관리</title>
<style>
 body{font-family:'Malgun Gothic',sans-serif;margin:0;background:#f4f5f7;color:#222}
 header{background:#1877f2;color:#fff;padding:12px 18px;font-size:18px;font-weight:700}
 .wrap{padding:14px 18px}
 .card{background:#fff;border:1px solid #e2e4e8;border-radius:8px;padding:14px;margin-bottom:12px}
 .step{font-weight:700;margin-bottom:6px}
 button{background:#1877f2;color:#fff;border:0;border-radius:6px;padding:8px 12px;cursor:pointer;font-size:13px}
 button.gray{background:#65676b} button.red{background:#e0245e} button.orange{background:#f5a623}
 button:disabled{opacity:.5;cursor:default}
 textarea{width:100%;height:64px;box-sizing:border-box;border:1px solid #ccd0d5;border-radius:6px;padding:8px;font-size:13px}
 input,select{border:1px solid #ccd0d5;border-radius:6px;padding:6px;font-size:13px}
 table{width:100%;border-collapse:collapse;background:#fff;font-size:13px}
 th,td{border-bottom:1px solid #eee;padding:7px 8px;text-align:left;vertical-align:top}
 th{background:#f0f2f5;position:sticky;top:0}
 tr:hover{background:#f7f9fc}
 .tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;color:#fff}
 .ig{background:#c13584}.fb{background:#1877f2}
 #status{color:#444;font-size:13px;margin-left:10px}
 .bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
</style></head><body>
<header>댓글 통합관리 — 인스타/페북 광고 댓글</header>
<div class=wrap>
 <div class=card>
   <div class=step>① 로그인 (최초 1회)</div>
   <div class=bar><button id=loginBtn onclick="doLogin()">로그인 브라우저 열기</button>
   <span id=loginStatus>확인 중...</span></div>
 </div>
 <div class=card>
   <div class=step>② 관리할 계정 '받은메시지함' 링크 붙여넣기 (한 줄에 하나)</div>
   <textarea id=links placeholder="https://business.facebook.com/latest/inbox/instagram?...asset_id=페이지ID..."></textarea>
   <div class=bar style="margin-top:6px">
     <button onclick="register()">계정 등록</button>
     <button class=orange onclick="collect()" id=collectBtn>③ 댓글 수집</button>
     <span id=accinfo></span>
   </div>
 </div>
 <div class=card>
   <div class=bar>
     <label>매체 <select id=fplat onchange=render()><option>전체</option><option>IG</option><option>FB</option></select></label>
     <input id=fkw placeholder=검색 oninput=render()>
     <button class=gray onclick="checkAll(true)">전체선택</button>
     <button class=gray onclick="checkAll(false)">해제</button>
     <span style="flex:1"></span>
     <button class=red onclick="act('delete')">선택 삭제</button>
     <button class=orange onclick="act('hide')">선택 숨기기</button>
     <button onclick="act('block')">선택 차단</button>
     <span id=status></span>
   </div>
 </div>
 <div class=card style="padding:0;max-height:60vh;overflow:auto">
   <table><thead><tr><th></th><th>브랜드</th><th>계정</th><th>매체</th><th>게시물</th><th>작성자</th><th>댓글</th><th>좋아요</th><th>시간</th></tr></thead>
   <tbody id=tb></tbody></table>
 </div>
</div>
<script>
let rows=[], checked=new Set();
function setStatus(m){document.getElementById('status').textContent=m}
async function api(path,body){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});return r.json()}
async function doLogin(){await api('login');setTimeout(checkLogin,2500);}
async function checkLogin(){
  let s;try{s=await(await fetch('/api/login_status')).json()}catch(e){return}
  const el=document.getElementById('loginStatus'),btn=document.getElementById('loginBtn');
  if(s.logged_in){el.textContent='✅ 로그인 완료';el.style.color='#1a9e4b';el.style.fontWeight='700';btn.textContent='로그인 브라우저 다시 열기';}
  else if(s.browser){el.textContent='⏳ 브라우저 열림 — 그 창에서 로그인하세요';el.style.color='#f5a623';el.style.fontWeight='700';}
  else{el.textContent='❌ 아직 로그인 안 됨 — 왼쪽 버튼을 누르세요';el.style.color='#e0245e';el.style.fontWeight='700';}
}
setInterval(checkLogin,3000);checkLogin();
async function loadComments(){const r=await fetch('/api/comments');rows=await r.json();checked.clear();render();document.getElementById('accinfo').textContent='등록 계정: '+(await (await fetch('/api/accounts')).json()).count+'개';}
function render(){
  const plat=document.getElementById('fplat').value, kw=document.getElementById('fkw').value.toLowerCase();
  const tb=document.getElementById('tb');tb.innerHTML='';let n=0;
  rows.forEach((r,i)=>{
    if(plat!=='전체'&&r.plat!==plat)return;
    if(kw&&!(r.text||'').toLowerCase().includes(kw)&&!(r.author||'').toLowerCase().includes(kw))return;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><input type=checkbox ${checked.has(i)?'checked':''} onchange="tog(${i})"></td>
      <td>${r.brand||''}</td><td>${r.account||''}</td>
      <td><span class="tag ${r.plat==='IG'?'ig':'fb'}">${r.plat}</span></td>
      <td>${(r.post||'').split(' | ')[0].slice(0,26)}</td>
      <td>${r.author||''}</td><td>${(r.text||'').replace(/</g,'&lt;')}</td>
      <td>${r.likes||''}</td><td>${r.time||''}</td>`;
    tb.appendChild(tr);n++;
  });
  setStatus(`표시 ${n} / 전체 ${rows.length} / 선택 ${checked.size}`);
}
function tog(i){checked.has(i)?checked.delete(i):checked.add(i);setStatus(`선택 ${checked.size}`)}
function checkAll(on){rows.forEach((r,i)=>{on?checked.add(i):checked.delete(i)});render()}
async function register(){const t=document.getElementById('links').value;const r=await api('register',{links:t});alert(r.msg);loadComments();}
async function collect(){document.getElementById('collectBtn').disabled=true;setStatus('수집 중... (계정 순회, 수십 초)');await api('collect');poll();}
async function poll(){const s=await (await fetch('/api/collect_status')).json();setStatus(s.msg);if(s.running){setTimeout(poll,2000);}else{document.getElementById('collectBtn').disabled=false;loadComments();}}
async function act(action){
  const sel=[...checked].map(i=>rows[i]).filter(Boolean);
  if(!sel.length){alert('댓글을 선택하세요');return;}
  const word={delete:'삭제',hide:'숨기기',block:'차단'}[action];
  if((action==='delete'||action==='block')&&!confirm(`선택 ${sel.length}개를 ${word}합니다. 진행?`))return;
  let done=0,ver=0;
  for(let k=0;k<sel.length;k++){setStatus(`${word} ${k+1}/${sel.length}: @${sel[k].author}`);
    const r=await api('action',{row:sel[k],action});if(r.done){done++;if(r.verified)ver++;}
  }
  setStatus(`${word}: 실행 ${done}/${sel.length}, 사라짐확인 ${ver}`);checked.clear();loadComments();
}
loadComments();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/":
            self._send(200, INDEX_HTML, "text/html")
        elif p == "/api/comments":
            self._send(200, json.dumps(get_rows(), ensure_ascii=False))
        elif p == "/api/accounts":
            self._send(200, json.dumps({"count": len(load_accounts_file()["accounts"])}))
        elif p == "/api/collect_status":
            self._send(200, json.dumps(COLLECT_STATE))
        elif p == "/api/login_status":
            self._send(200, json.dumps(check_login()))
        else:
            self._send(404, "{}")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        ln = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(ln) or "{}") if ln else {}
        if p == "/api/login":
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            subprocess.Popen([sys.executable, os.path.join(BASE, "biz_inbox.py"), "open"], cwd=BASE, env=env)
            self._send(200, json.dumps({"ok": True}))
        elif p == "/api/register":
            conf = load_accounts_file()
            existing = {a["page_id"] for a in conf["accounts"]}
            added = 0
            for line in (body.get("links") or "").splitlines():
                biz, pid = parse_link(line)
                if not pid or pid in existing:
                    continue
                if not conf.get("business_id") and biz:
                    conf["business_id"] = biz
                conf["accounts"].append({"brand": "", "ig": pid, "page_name": "(링크등록)",
                                         "page_id": pid, "business_id": biz})
                existing.add(pid); added += 1
            json.dump(conf, open(ACCF, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            self._send(200, json.dumps({"msg": f"계정 {added}개 등록됨 (총 {len(conf['accounts'])}개). ③수집을 누르세요."}))
        elif p == "/api/collect":
            if not COLLECT_STATE["running"]:
                threading.Thread(target=run_collect, daemon=True).start()
            self._send(200, json.dumps({"ok": True}))
        elif p == "/api/action":
            r = body.get("row", {}); action = body.get("action")
            try:
                res = inbox_actions.do_action(r.get("page_id"), r.get("plat"), r.get("post"),
                                              r.get("author"), action, log=lambda m: None,
                                              business_id=r.get("business_id"))
                self._send(200, json.dumps(res or {"done": False}))
            except Exception as e:
                self._send(200, json.dumps({"done": False, "error": str(e)}))
        else:
            self._send(404, "{}")


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"댓글 통합관리 웹앱: http://localhost:{PORT}", flush=True)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
