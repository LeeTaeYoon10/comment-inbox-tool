# -*- coding: utf-8 -*-
"""
Meta Business Suite 받은메시지함(받은 댓글) 자동화 - 브라우저 조종.
- 비즈니스 계정 로그인 1번(프로필 저장) → 모든 계정 광고/게시물 댓글이 한 곳에.
- CDP 9222로 열어두고 조종.

python biz_inbox.py open   # 받은메시지함 열기(로그인 대기)
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, "bizprofile")
SHOTS = os.path.join(BASE, "shots")

# 로그인용 일반 진입(어느 계정이든 여기서 로그인). 계정별 이동은 툴이 알아서 함.
INBOX_URL = "https://business.facebook.com/latest/home"


def main():
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=False, channel="chrome",
            viewport={"width": 1500, "height": 950}, locale="ko-KR",
            args=["--remote-debugging-port=9222",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(INBOX_URL, wait_until="domcontentloaded")
        print("받은메시지함 여는 중. 로그인 필요하면 창에서 직접 로그인하세요.", flush=True)
        print("CDP 9222 유지. 창을 닫기 전까지 계속 유지합니다.", flush=True)
        while True:
            time.sleep(3600)
        ctx.close()


if __name__ == "__main__":
    main()
