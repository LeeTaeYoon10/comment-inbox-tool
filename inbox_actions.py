# -*- coding: utf-8 -*-
"""
받은메시지함에서 특정 댓글에 대해 삭제/숨기기/차단 실행 (CDP 9222 세션 조종).
GUI에서 호출.
"""
import json
import os
import time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
CDP = "http://127.0.0.1:9222"


def _biz():
    with open(os.path.join(BASE, "inbox_accounts.json"), "r", encoding="utf-8") as f:
        return json.load(f)["business_id"]


def _inbox_url(biz, page_id, platform):
    # business_id 생략 → 메타가 올바른 포트폴리오로 자동 해결
    return (f"https://business.facebook.com/latest/inbox/{platform}"
            f"?page_id={page_id}&asset_id={page_id}&mailbox_id={page_id}")


FIND_THREAD_JS = r"""(preview)=>{
  // preview 세그먼트 중 가장 구별되는 것(날짜/일반명 제외)을 키로
  const segs=preview.split(' | ').map(s=>s.trim());
  let key=null;
  for(const s of segs){
    if(!s) continue;
    if(/^(Instagram|Facebook)/.test(s)) continue;
    if(/^\d+월|^\d+일|^\d+주/.test(s)) continue;
    key=s.slice(0,22); break;
  }
  if(!key) key=segs[0].slice(0,22);
  for(const e of document.querySelectorAll('div,li')){
    const t=(e.innerText||'').trim(); const r=e.getBoundingClientRect();
    if(r.left<460&&r.left>40&&r.width>150&&r.height>40&&r.height<110&&r.top>180&&t.includes(key)){
      return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), key:key};
    }
  }
  return null;
}"""

# 특정 작성자 댓글 행에 호버 후 그 행의 '...'(w<24 아이콘버튼) 좌표
FIND_DOTS_JS = r"""(author)=>{
  const kw=/좋아요|답글 달기|메시지|관리|숨기기|·/;
  let a=null;
  for(const e of document.querySelectorAll('div,span,a')){
    const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    const r=e.getBoundingClientRect();
    if(own===author && r.left>=540 && r.left<=900 && r.top>240 && r.top<860){ a={top:r.top,left:r.left}; break; }
  }
  if(!a) return null;
  // 그 댓글 근처(top-12~+55)의 작은 아이콘버튼(...) 중 가장 오른쪽 (IG·FB 모두)
  let dots=null;
  for(const e of document.querySelectorAll('[role=button],button,a,div,i')){
    const r=e.getBoundingClientRect();
    if(r.top>a.top-12 && r.top<a.top+55 && r.left>640 && r.width>0 && r.width<26 && r.height>0 && r.height<26){
      if(!dots || r.left>dots.left) dots={left:r.left, top:r.top, w:r.width};
    }
  }
  return {authorTop:Math.round(a.top), authorLeft:Math.round(a.left),
          dots: dots?{x:Math.round(dots.left+dots.w/2), y:Math.round(dots.top+dots.w/2)}:null};
}"""

# 작성자로 댓글 행을 찾아 그 '...'(관리/더보기) 버튼 좌표 반환
FIND_COMMENT_JS = r"""(author)=>{
  const kw=/좋아요|답글 달기|메시지|관리|숨기기/;
  let a=null;
  for(const e of document.querySelectorAll('div,span,a')){
    const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    const r=e.getBoundingClientRect();
    if(own===author && r.left>=540 && r.left<=900 && r.top>240 && r.top<860){ a={top:r.top,left:r.left}; break; }
  }
  if(!a) return null;
  return {authorTop:Math.round(a.top), authorLeft:Math.round(a.left)};
}"""

SCRAPE_AUTHORS_JS = r"""()=>{
  const kw=/좋아요|답글 달기|메시지|관리|숨기기|·/;
  const out=[];
  for(const e of document.querySelectorAll('div,span,a')){
    const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    const r=e.getBoundingClientRect();
    if(own && r.left>=540 && r.left<=900 && r.top>240 && r.top<860 && !kw.test(own) && own.length<40) out.push(own);
  }
  return out;
}"""

MENU_ITEM_JS = r"""(labelRe)=>{
  const re=new RegExp(labelRe);
  for(const e of document.querySelectorAll('div,span,a,[role=menuitem]')){
    const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    const r=e.getBoundingClientRect();
    if(own && own.length<20 && re.test(own) && r.width>0 && r.height>0){
      return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), label:own};
    }
  }
  return null;
}"""


def do_action(page_id, platform, post_preview, author, action, log=print, business_id=None):
    """action: 'delete' | 'hide' | 'block'"""
    biz = business_id or _biz()
    plat = "instagram" if platform == "IG" else "facebook"
    tab = "Instagram 댓글" if platform == "IG" else "Facebook 댓글"
    label_re = {"delete": "삭제", "hide": "숨기", "block": "차단|제한"}[action]

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        page = b.contexts[0].pages[0]
        page.goto(_inbox_url(biz, page_id, plat), wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        # 탭
        page.evaluate("""(nm)=>{for(const e of document.querySelectorAll('div,span,a')){if((e.innerText||'').trim()===nm){e.click();return;}}}""", tab)
        page.wait_for_timeout(3000)
        # 스레드 열기
        th = page.evaluate(FIND_THREAD_JS, post_preview)
        if not th:
            log("스레드를 못 찾음"); return False
        log(f"스레드 열림(key={th.get('key')})")
        page.mouse.click(th["x"], th["y"]); page.wait_for_timeout(4500)
        # 댓글 행 찾기
        c = page.evaluate(FIND_COMMENT_JS, author)
        if not c:
            log(f"댓글(@{author})을 못 찾음 — 스레드 안에 없음"); return False
        # 그 댓글 텍스트 위에 호버 → '...' 버튼 노출
        page.mouse.move(c["authorLeft"] + 130, c["authorTop"] + 1)
        page.wait_for_timeout(1200)
        d = page.evaluate(FIND_DOTS_JS, author)
        if not d or not d.get("dots"):
            # 폴백: 관례 위치
            page.mouse.click(793, c["authorTop"] + 28)
        else:
            page.mouse.click(d["dots"]["x"], d["dots"]["y"])
        page.wait_for_timeout(1800)
        # 메뉴에서 해당 액션 클릭
        mi = page.evaluate(MENU_ITEM_JS, label_re)
        if not mi:
            log(f"메뉴에 '{label_re}' 항목 없음"); return False
        page.mouse.click(mi["x"], mi["y"]); page.wait_for_timeout(1500)
        # 확인 다이얼로그(삭제/차단 확인 버튼)
        confirm = page.evaluate(MENU_ITEM_JS, "삭제|차단|확인|숨기기")
        if confirm and action in ("delete", "block"):
            page.mouse.click(confirm["x"], confirm["y"]); page.wait_for_timeout(1400)
        # 검증: 스레드 다시 읽어 그 작성자 댓글이 남아있는지
        page.wait_for_timeout(1500)
        authors_now = page.evaluate(SCRAPE_AUTHORS_JS)
        verified = author not in authors_now
        log(f"[{action}] @{author} 처리 완료 · 검증: {'사라짐(확인)' if verified else '아직 보임(미확인)'}")
        return {"done": True, "verified": verified}


if __name__ == "__main__":
    import sys
    # 테스트: do_action(page_id, platform, post_preview, author, action)
    print("모듈. GUI에서 호출하세요.")
