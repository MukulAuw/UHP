"""Open each Streamlit Community Cloud app in a real browser; click the wake button if it's asleep.
APP_URLS: comma-separated app URLs, e.g. https://paywall-db.streamlit.app,https://au-subs.streamlit.app
"""
import os, re, sys
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

urls = [u.strip() for u in os.environ.get("APP_URLS", "").split(",") if u.strip()]
if not urls:
    sys.exit("APP_URLS is empty")

failed = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for url in urls:
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            btn = page.get_by_role("button", name=re.compile("get this app back up", re.I))
            try:
                btn.wait_for(timeout=15000)
                asleep = True
            except PWTimeout:
                asleep = False
            if asleep:
                btn.click()
                btn.wait_for(state="hidden", timeout=180000)   # app is booting
                print(f"{url}: was asleep, woken")
            else:
                print(f"{url}: awake")
            page.wait_for_timeout(30000)   # stay connected so the visit counts as traffic
        except Exception as e:
            print(f"{url}: FAILED {e}")
            failed.append(url)
        finally:
            page.close()
    browser.close()

sys.exit(1 if failed else 0)   # a red run = GitHub emails you
