# -*- coding: utf-8 -*-
"""
받은메시지함 댓글 통합 관리 GUI (팀 공유용).
파일 실행하면 바로: ① 로그인 브라우저 열기 → ② 관리계정 링크 붙여넣기 → ③ 댓글 수집 → 삭제/숨김/차단.

python inbox_manager.py
"""
import json
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
import urllib.parse
from tkinter import ttk, messagebox

import inbox_actions

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "inbox_comments.json")
ACCF = os.path.join(BASE, "inbox_accounts.json")


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
    """Business Suite 받은메시지함 링크에서 business_id, page_id 추출."""
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url.strip()).query)
    except Exception:
        return None, None
    biz = (q.get("business_id") or [None])[0]
    pid = (q.get("asset_id") or q.get("mailbox_id") or q.get("page_id") or [None])[0]
    return biz, pid


def load_accounts_file():
    if os.path.exists(ACCF):
        try:
            return json.load(open(ACCF, encoding="utf-8"))
        except Exception:
            pass
    return {"business_id": "", "accounts": []}


class App:
    def __init__(self, root):
        self.root = root
        root.title("댓글 통합관리 — 인스타/페북 광고댓글")
        root.geometry("1250x760")
        self.rows = []
        self.checked = set()
        self._build()
        self.load()

    def _build(self):
        # ===== 설정 패널(상단) =====
        setup = ttk.LabelFrame(self.root, text="시작하기", padding=8)
        setup.pack(fill="x", padx=6, pady=(6, 2))

        r1 = ttk.Frame(setup); r1.pack(fill="x")
        ttk.Button(r1, text="① 로그인 브라우저 열기", command=self.open_login).pack(side="left")
        ttk.Label(r1, text="  (처음 1회: 열린 크롬에서 Business Suite 로그인)").pack(side="left")

        r2 = ttk.Frame(setup); r2.pack(fill="x", pady=(6, 0))
        ttk.Label(r2, text="② 관리할 계정 '받은메시지함' 링크 붙여넣기 (한 줄에 하나):").pack(anchor="w")
        self.links = tk.Text(setup, height=3, width=120)
        self.links.pack(fill="x", pady=2)
        r3 = ttk.Frame(setup); r3.pack(fill="x")
        ttk.Button(r3, text="계정 등록", command=self.register_links).pack(side="left")
        ttk.Button(r3, text="③ 댓글 수집(전 계정)", command=self.refresh).pack(side="left", padx=6)
        self.acc_lbl = tk.StringVar(value="")
        ttk.Label(r3, textvariable=self.acc_lbl).pack(side="left", padx=10)

        # ===== 필터/액션 =====
        bar = ttk.Frame(self.root, padding=6); bar.pack(fill="x")
        ttk.Label(bar, text="매체").pack(side="left")
        self.f_plat = tk.StringVar(value="전체")
        ttk.Combobox(bar, textvariable=self.f_plat, values=["전체", "IG", "FB"], width=5,
                     state="readonly").pack(side="left", padx=4)
        ttk.Label(bar, text="검색").pack(side="left")
        self.f_kw = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.f_kw, width=18); e.pack(side="left", padx=4)
        e.bind("<Return>", lambda _e: self.render())
        ttk.Button(bar, text="필터", command=self.render).pack(side="left")
        ttk.Button(bar, text="전체선택", command=lambda: self.check_all(True)).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text="해제", command=lambda: self.check_all(False)).pack(side="left", padx=4)
        ttk.Button(bar, text="선택 차단", command=lambda: self.act("block")).pack(side="right")
        ttk.Button(bar, text="선택 숨기기", command=lambda: self.act("hide")).pack(side="right", padx=6)
        ttk.Button(bar, text="선택 삭제", command=lambda: self.act("delete")).pack(side="right")

        # ===== 표 =====
        cols = ("chk", "brand", "account", "plat", "post", "author", "text", "likes", "time")
        head = {"chk": ("✓", 30), "brand": ("브랜드", 60), "account": ("계정", 130),
                "plat": ("매체", 45), "post": ("게시물", 190), "author": ("작성자", 130),
                "text": ("댓글", 360), "likes": ("좋아요", 55), "time": ("시간", 55)}
        wrap = ttk.Frame(self.root); wrap.pack(fill="both", expand=True, padx=6)
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="none")
        for c, (h, w) in head.items():
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w" if c in ("post", "text", "author", "account") else "center",
                             stretch=(c == "text"))
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True); vs.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_click)

        self.status = tk.StringVar(value="준비됨 — ①로그인 → ②링크등록 → ③수집")
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w",
                  padding=4).pack(fill="x", side="bottom")
        self.update_acc_label()

    # ---------- 설정 동작 ----------
    def open_login(self):
        self.set("로그인 브라우저 여는 중... 열린 크롬에서 Business Suite 로그인하세요.")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        subprocess.Popen([sys.executable, os.path.join(BASE, "biz_inbox.py"), "open"],
                         cwd=BASE, env=env)

    def register_links(self):
        text = self.links.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("안내", "링크를 붙여넣으세요"); return
        conf = load_accounts_file()
        existing = {a["page_id"] for a in conf["accounts"]}
        added = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            biz, pid = parse_link(line)
            if not pid:
                continue
            if not conf.get("business_id") and biz:
                conf["business_id"] = biz
            if pid in existing:
                continue
            conf["accounts"].append({"brand": "", "ig": pid, "page_name": "(링크등록)",
                                     "page_id": pid, "business_id": biz})
            existing.add(pid); added += 1
        json.dump(conf, open(ACCF, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        self.update_acc_label()
        messagebox.showinfo("완료", f"계정 {added}개 등록됨 (총 {len(conf['accounts'])}개)\n"
                                    f"③ 댓글 수집을 누르세요.")

    def update_acc_label(self):
        conf = load_accounts_file()
        self.acc_lbl.set(f"등록 계정: {len(conf['accounts'])}개")

    # ---------- 데이터 ----------
    def load(self):
        if not os.path.exists(DATA):
            self.rows = []; self.render(); return
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
                    "page_id": pid, "business_id": pid_biz.get(pid),
                    "post": post["post_preview"], "author": c["author"],
                    "text": c["text"], "likes": c.get("likes", ""), "time": c.get("time", ""),
                })
        rows.sort(key=lambda r: approx_days(r["time"]))
        self.rows = rows
        self.render()
        self.set(f"댓글 {len(rows)}개 로드 (최신순)")

    def render(self):
        self.tree.delete(*self.tree.get_children())
        plat = self.f_plat.get(); kw = self.f_kw.get().strip().lower()
        n = 0
        for i, r in enumerate(self.rows):
            if plat != "전체" and r["plat"] != plat:
                continue
            if kw and kw not in (r["text"] or "").lower() and kw not in (r["author"] or "").lower():
                continue
            iid = str(i)
            mark = "✓" if iid in self.checked else ""
            self.tree.insert("", "end", iid=iid, values=(
                mark, r["brand"], r["account"], r["plat"], (r["post"] or "").split(" | ")[0][:26],
                r["author"], (r["text"] or "").replace("\n", " "), r["likes"], r["time"]))
            n += 1
        self.set(f"표시 {n} / 전체 {len(self.rows)} / 선택 {len(self.checked)}")

    def on_click(self, ev):
        if self.tree.identify("region", ev.x, ev.y) != "cell":
            return
        iid = self.tree.identify_row(ev.y)
        if not iid:
            return
        if iid in self.checked:
            self.checked.discard(iid); self.tree.set(iid, "chk", "")
        else:
            self.checked.add(iid); self.tree.set(iid, "chk", "✓")
        self.set(f"선택 {len(self.checked)}")

    def check_all(self, on):
        for iid in self.tree.get_children():
            if on:
                self.checked.add(iid); self.tree.set(iid, "chk", "✓")
            else:
                self.checked.discard(iid); self.tree.set(iid, "chk", "")
        self.set(f"선택 {len(self.checked)}")

    def selected(self):
        return [self.rows[int(i)] for i in self.checked if int(i) < len(self.rows)]

    # ---------- 액션 ----------
    def act(self, action):
        rows = self.selected()
        if not rows:
            messagebox.showinfo("안내", "댓글을 선택하세요"); return
        word = {"delete": "삭제", "hide": "숨기기", "block": "차단"}[action]
        if action in ("delete", "block") and not messagebox.askyesno(
                "확인", f"선택 {len(rows)}개를 {word}합니다. 진행?"):
            return
        threading.Thread(target=self._act_worker, args=(rows, action, word), daemon=True).start()

    def _act_worker(self, rows, action, word):
        done, verified = 0, 0
        for i, r in enumerate(rows, 1):
            self.set(f"{word} {i}/{len(rows)}: @{r['author']}")
            try:
                res = inbox_actions.do_action(r["page_id"], r["plat"], r["post"], r["author"],
                                              action, log=lambda m: self.set(m),
                                              business_id=r.get("business_id"))
                if res and res.get("done"):
                    done += 1
                    if res.get("verified"):
                        verified += 1
                    self.root.after(0, lambda rr=r: self._remove_row(rr))
            except Exception as e:
                self.set(f"오류: {e}")
        self.checked.clear()
        self.root.after(0, lambda: messagebox.showinfo(
            "결과", f"{word}: 실행 {done}/{len(rows)}건, 사라짐 확인 {verified}건"))

    def _remove_row(self, row):
        if row in self.rows:
            self.rows.remove(row)
        self.render()

    # ---------- 수집 ----------
    def refresh(self):
        self.set("전 계정 수집 중... (계정 순회, 수십 초 소요)")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        try:
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, os.path.join(BASE, "inbox_collect.py")],
                               cwd=BASE, env=env, timeout=900, capture_output=True, text=True)
            self.root.after(0, self.load)
            if r.returncode != 0:
                self.set("수집 경고: 일부 실패(로그인/링크 확인)")
        except Exception as e:
            self.set(f"수집 오류: {e}")

    def set(self, msg):
        self.status.set(msg); self.root.update_idletasks()


def main():
    root = tk.Tk(); App(root); root.mainloop()


if __name__ == "__main__":
    main()
