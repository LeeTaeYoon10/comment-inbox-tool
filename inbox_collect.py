# -*- coding: utf-8 -*-
"""
5개 계정 x (Instagram 댓글 + Facebook 댓글) 받은메시지함 순회 → 댓글 통합 수집.
CDP 9222(로그인된 Business Suite 세션) 재사용.
결과: inbox_comments.json  (게시물별 댓글, 계정/플랫폼 태그, 수집순=최신 게시물부터)

python inbox_collect.py
"""
import json
import os
import time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
CDP = "http://127.0.0.1:9222"
BIZ = None


def load_accounts():
    with open(os.path.join(BASE, "inbox_accounts.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    return d["business_id"], d["accounts"]


def inbox_url(biz, page_id, platform):
    # platform: 'instagram' or 'facebook'
    # business_id 생략 → 메타가 그 페이지의 올바른 포트폴리오로 자동 해결(포트폴리오 무관 동작)
    return (f"https://business.facebook.com/latest/inbox/{platform}"
            f"?page_id={page_id}&asset_id={page_id}&mailbox_id={page_id}")


TAB_JS = """(nm)=>{
  for(const e of document.querySelectorAll('div,span,a,[role=tab]')){
    if((e.innerText||'').trim()===nm){ e.click(); return true; }
  }
  return false;
}"""

THREADS_JS = r"""()=>{
  // 같은 스레드(동일 preview)는 '가장 작은 요소'(=리스트 항목)만 채택.
  // FB 광고댓글 스레드는 펼쳐지면 700px+가 되므로 높이 상한을 넉넉히 두되 최소요소를 클릭타깃으로.
  const map={};
  for(const e of document.querySelectorAll('div,li')){
    const t=(e.innerText||'').trim();
    const r=e.getBoundingClientRect();
    if(r.left<460 && r.left>40 && r.width>150 && r.top>180 && r.height>36 && r.height<900){
      if(t.includes('아직') && t.includes('댓글이 없')) continue;
      if(t.includes('페이지 댓글') && t.includes('그룹 댓글')) continue; // 필터 헤더 제외
      const hasC = t.includes('댓글을 남') || t.includes('commented') || /님,/.test(t);
      if(!hasC) continue;
      const key = t.replace(/\s+/g,' ').slice(0,50);
      if(!map[key] || r.height < map[key].h){
        map[key] = {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2),
                    h:r.height, preview:t.replace(/\n/g,' | ').slice(0,90)};
      }
    }
  }
  return Object.values(map);
}"""

# 댓글 파싱: IG(작성자 left~571, 텍스트 같은줄 옆) + FB(작성자 left~811, 텍스트 아래줄) 둘 다.
# 진짜 댓글은 아래에 '좋아요/답글 달기' 액션줄이 있는 것만 채택(캡션·링크 오탐 방지).
COMMENTS_JS = r"""()=>{
  const nodes=[];
  for(const e of document.querySelectorAll('div,span,a')){
    const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    const r=e.getBoundingClientRect();
    if(own && r.left>460 && r.left<1520 && r.top>240 && r.top<870 && r.width>0 && r.height>0 && own.length<300){
      nodes.push({top:Math.round(r.top), left:Math.round(r.left), text:own});
    }
  }
  const kw=/좋아요|답글 달기|답장|메시지|관리|숨기기|숨기기 취소|더 보기|번역|최신순|·$/;
  const isTime=s=>/^\d+(주|일|시간|분|초|년)$/.test(s);
  const authors=nodes.filter(n=>n.left>=540 && n.left<=900 && !kw.test(n.text) && !isTime(n.text)
                              && n.text.length>=1 && n.text.length<=30 && !/이름으로/.test(n.text));
  const rows=[]; const seen=new Set();
  for(const a of authors){
    // 진짜 댓글 확인: 작성자 아래 8~60px에 좋아요/답글/숨기기 액션줄
    let hasAction=false;
    for(const n of nodes){ if(n.top>a.top+2 && n.top<a.top+62 && /좋아요|답글 달기|숨기기/.test(n.text)) hasAction=true; }
    if(!hasAction) continue;
    // 텍스트: (IG) 같은 top 오른쪽  또는  (FB) 바로 아래줄 같은 left
    let txt='';
    for(const n of nodes){
      if(Math.abs(n.top-a.top)<=12 && n.left>a.left+25 && !kw.test(n.text) && !isTime(n.text)){ txt=(txt+' '+n.text).trim(); }
    }
    if(!txt){
      for(const n of nodes){
        if(n.top>a.top+3 && n.top<a.top+32 && Math.abs(n.left-a.left)<60 && !kw.test(n.text) && !isTime(n.text) && n.text.length>2){ txt=n.text; break; }
      }
    }
    if(!txt) continue;
    const key=a.text+'|'+txt.slice(0,15);
    if(seen.has(key)) continue; seen.add(key);
    let likes='', tm='';
    for(const n of nodes){
      if(n.top>a.top-14 && n.top<a.top+50){
        if(/^좋아요/.test(n.text)) likes=n.text;
        if(isTime(n.text) && !tm) tm=n.text;
      }
    }
    rows.push({author:a.text, text:txt, likes:likes, time:tm, y:a.top});
  }
  rows.sort((x,y)=>x.y-y.y);
  return rows;
}"""


def collect_tab(page, platform_label, acc):
    tab = "Instagram 댓글" if platform_label == "IG" else "Facebook 댓글"
    # 탭이 로드될 때까지 재시도 클릭
    ok = False
    for _ in range(5):
        ok = page.evaluate(TAB_JS, tab)
        page.wait_for_timeout(2500)
        if ok:
            break
    page.wait_for_timeout(2500)
    threads = page.evaluate(THREADS_JS)
    result = []
    for th in threads[:15]:
        try:
            page.mouse.click(th["x"], th["y"])
            page.wait_for_timeout(4500)
            comments = page.evaluate(COMMENTS_JS)
        except Exception as e:
            comments = []
        if comments:
            result.append({
                "brand": acc.get("brand", ""), "account": acc.get("ig", acc["page_id"]),
                "page_name": acc.get("page_name", ""), "page_id": acc["page_id"],
                "platform": platform_label, "post_preview": th["preview"],
                "comments": comments,
            })
    return result


def main():
    biz, accounts = load_accounts()
    all_posts = []
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP)
        page = b.contexts[0].pages[0]
        for acc in accounts:
            acc_biz = acc.get("business_id") or biz
            for platform in ("instagram", "facebook"):
                label = "IG" if platform == "instagram" else "FB"
                url = inbox_url(acc_biz, acc["page_id"], platform)
                try:
                    # SPA 소프트내비 방지 → 빈페이지 거쳐 강제 풀로드
                    page.goto("about:blank")
                    page.wait_for_timeout(500)
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(8000)
                    if "login" in page.url:
                        print(f"[{acc['ig']}/{label}] 로그인필요 — 세션 확인"); continue
                    posts = collect_tab(page, label, acc)
                    print(f"[{acc['brand']}/@{acc['ig']}/{label}] 댓글있는 게시물 {len(posts)}개")
                    all_posts.extend(posts)
                except Exception as e:
                    print(f"[{acc['ig']}/{label}] 오류: {e}")
    with open(os.path.join(BASE, "inbox_comments.json"), "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)
    total = sum(len(p["comments"]) for p in all_posts)
    print(f"\n총 게시물 {len(all_posts)}개, 댓글 {total}개 → inbox_comments.json")


if __name__ == "__main__":
    main()
