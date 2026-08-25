# -*- coding: utf-8 -*-
"""특정 계정 받은메시지함에서 특정 작성자 댓글이 남아있는지 확인. CDP 9222."""
import sys
from playwright.sync_api import sync_playwright

BIZ = "2322412481432916"


def main():
    page_id = sys.argv[1]
    platform = sys.argv[2]   # instagram / facebook
    author = sys.argv[3]
    tab = "Instagram 댓글" if platform == "instagram" else "Facebook 댓글"
    url = (f"https://business.facebook.com/latest/inbox/{platform}"
           f"?business_id={BIZ}&page_id={page_id}&asset_id={page_id}&mailbox_id={page_id}")
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = b.contexts[0].pages[0]
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        page.evaluate("""(nm)=>{for(const e of document.querySelectorAll('div,span,a')){if((e.innerText||'').trim()===nm){e.click();return;}}}""", tab)
        page.wait_for_timeout(3000)
        threads = page.evaluate(r"""()=>{
          const out=[];const seen=new Set();
          for(const e of document.querySelectorAll('div,li')){const t=(e.innerText||'').trim();const r=e.getBoundingClientRect();
            if(r.left<460&&r.left>40&&r.width>150&&r.height>40&&r.height<110&&r.top>180){
              if(t.includes('아직')&&t.includes('댓글이 없'))continue;
              const hasC=t.includes('댓글을 남')||t.includes('commented')||/님,/.test(t); if(!hasC)continue;
              const k=t.replace(/\s+/g,' ').slice(0,40); if(seen.has(k))continue; seen.add(k);
              out.push({x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)});
            }}
          return out;
        }""")
        found = False
        seen_authors = set()
        for th in threads[:12]:
            page.mouse.click(th["x"], th["y"])
            page.wait_for_timeout(4000)
            authors = page.evaluate(r"""()=>{const kw=/좋아요|답글 달기|메시지|관리|숨기기|·/;const out=[];
              for(const e of document.querySelectorAll('div,span,a')){const own=Array.from(e.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();const r=e.getBoundingClientRect();
                if(own&&r.left>=550&&r.left<=610&&r.top>240&&r.top<860&&!kw.test(own)&&own.length<40)out.push(own);}return out;}""")
            for a in authors:
                seen_authors.add(a)
            if author in authors:
                found = True
        print(f"작성자 '{author}' 현재 존재: {found}")
        print(f"현재 보이는 작성자들: {sorted(seen_authors)}")


if __name__ == "__main__":
    main()
