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
CDP = "http://localhost:9222"
BIZ = None


def load_accounts():
    with open(os.path.join(BASE, "inbox_accounts.json"), "r", encoding="utf-8") as f:
        d = json.load(f)
    return d["business_id"], d["accounts"]


def inbox_url(biz, page_id, platform):
    # platform: 'instagram' or 'facebook'
    return (f"https://business.facebook.com/latest/inbox/{platform}"
            f"?business_id={biz}&page_id={page_id}&asset_id={page_id}&mailbox_id={page_id}")


TAB_JS = """(nm)=>{
  for(const e of document.querySelectorAll('div,span,a,[role=tab]')){
    if((e.innerText||'').trim()===nm){ e.click(); return true; }
  }
  return false;
}"""

THREADS_JS = r"""()=>{
  const out=[]; const seen=new Set();
  for(const e of document.querySelectorAll('div,li')){
    const t=(e.innerText||'').trim();
    const r=e.getBoundingClientRect();
    if(r.left<460 && r.left>40 && r.width>150 && r.height>40 && r.height<110 && r.top>180){
      if(t.includes('아직') && t.includes('댓글이 없')) continue;
      const hasC = t.includes('댓글을 남') || t.includes('commented') || /님,/.test(t);
      if(!hasC) continue;
      const key = t.replace(/\s+/g,' ').slice(0,50);
      if(seen.has(key)) continue; seen.add(key);
      out.push({x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2),
                preview:t.replace(/\n/g,' | ').slice(0,90)});
    }
  }
  return out;
}"""

# 댓글 파싱: 작성자(left 560~600) 기준, 같은 top±8의 text(left>600), 아래 좋아요/시간
COMMENTS_JS = r"""()=>{
  const nodes=[];
  for(const e of document.querySelectorAll('div,span,a')){
    const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    const r=e.getBoundingClientRect();
    if(own && r.left>460 && r.left<1520 && r.top>240 && r.top<860 && r.width>0 && r.height>0 && own.length<300){
      nodes.push({top:Math.round(r.top), left:Math.round(r.left), text:own});
    }
  }
  // 작성자 후보: left 555~605, 키워드 아님, 짧음
  const kw=/좋아요|답글 달기|메시지|관리|숨기기|더 보기|번역|·|^\d+주$|^\d+일$/;
  const authors=nodes.filter(n=>n.left>=550 && n.left<=610 && !kw.test(n.text) && n.text.length<40);
  const rows=[];
  for(const a of authors){
    // 같은 줄 텍스트: top±10, left>=605
    let txt='';
    for(const n of nodes){
      if(Math.abs(n.top-a.top)<=12 && n.left>=600 && !kw.test(n.text)){ txt=(txt+' '+n.text).trim(); }
    }
    // 좋아요/시간: 작성자 아래 5~45px
    let likes='', tm='';
    for(const n of nodes){
      if(n.top> a.top+8 && n.top< a.top+50){
        if(/^좋아요/.test(n.text)) likes=n.text;
        if(/^\d+(주|일|시간|분|초)$/.test(n.text) && !tm) tm=n.text;
      }
      if(/^\d+(주|일|시간|분|초)$/.test(n.text) && Math.abs(n.top-a.top)<=12 && !tm) tm=n.text;
    }
    if(txt) rows.push({author:a.text, text:txt, likes:likes, time:tm, y:a.top});
  }
  // top 순서(위=먼저 보이는 것)
  rows.sort((x,y)=>x.y-y.y);
  return rows;
}"""


def collect_tab(page, platform_label, acc):
    tab = "Instagram 댓글" if platform_label == "IG" else "Facebook 댓글"
    page.evaluate(TAB_JS, tab)
    page.wait_for_timeout(3500)
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
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(7000)
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
