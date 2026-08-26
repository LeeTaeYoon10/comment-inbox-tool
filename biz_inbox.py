# -*- coding: utf-8 -*-
"""
Meta Business Suite 로그인용 크롬 실행 (subprocess 직접 실행 방식).
- 크롬을 --remote-debugging-port=9222 로 직접 띄움(Playwright 파이프 충돌 없음).
- 다른 스크립트(수집/액션)는 127.0.0.1:9222 로 connect_over_cdp.
- 로그인 세션은 bizprofile 폴더에 저장(다음부터 자동 로그인 유지).

python biz_inbox.py open
"""
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, "bizprofile")
PORT = 9222
HOME = "https://business.facebook.com/latest/home"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome():
    for p in CHROME_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def cdp_alive():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def clean_locks():
    for f in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            os.remove(os.path.join(PROFILE, f))
        except Exception:
            pass


def main():
    # 이미 로그인 브라우저가 떠 있으면 중복 실행 안 함
    if cdp_alive():
        print("로그인 브라우저가 이미 열려 있습니다. 기존 창을 사용하세요.", flush=True)
        return
    chrome = find_chrome()
    if not chrome:
        print("[오류] Google Chrome을 찾을 수 없습니다. Chrome을 설치한 뒤 다시 실행하세요.", flush=True)
        return
    os.makedirs(PROFILE, exist_ok=True)
    clean_locks()  # 죽은 이전 세션이 남긴 잠금 제거
    try:
        subprocess.Popen([
            chrome,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
            HOME,
        ])
    except Exception as e:
        print(f"[오류] 크롬 실행 실패: {e}", flush=True)
        return
    # CDP가 뜰 때까지 잠깐 확인
    for _ in range(15):
        time.sleep(1)
        if cdp_alive():
            print("로그인 브라우저 열림. 그 창에서 Business Suite에 로그인하세요.", flush=True)
            return
    print("로그인 브라우저를 띄웠습니다. 창에서 로그인하세요.", flush=True)


if __name__ == "__main__":
    main()
