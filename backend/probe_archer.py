"""
Run this once to explore what the Archer reports page looks like after login
and what network requests it makes. Helps calibrate the scraper.

Usage:  python probe_archer.py
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))

from app.config import get_settings
settings = get_settings()

from playwright.sync_api import sync_playwright

LOGIN_URL   = "https://app.archeraffiliates.com/auth/sign-in"
REPORTS_URL = "https://app.archeraffiliates.com/reports"

api_calls = []

def on_response(response):
    if response.status == 200 and response.request.resource_type in ("fetch", "xhr"):
        try:
            body = response.json()
            api_calls.append({"url": response.url, "body": body})
        except Exception:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("response", on_response)

    print("Navigating to login page...")
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
    print("Login page title:", page.title(), "| URL:", page.url)

    print("Filling credentials...")
    page.fill('input[type="text"]',     settings.archer_username)
    page.fill('input[type="password"]', settings.archer_password)
    page.click('button[type="submit"]')

    page.wait_for_url(lambda url: "sign-in" not in url, timeout=15000)
    print("After login URL:", page.url)
    time.sleep(2)

    print("\nNavigating to reports page...")
    page.goto(REPORTS_URL, wait_until="networkidle", timeout=20000)
    time.sleep(3)

    print("Reports page URL:", page.url)
    print("Reports page title:", page.title())
    print("\nPage text (first 1000 chars):")
    print(page.inner_text("body")[:1000])

    print("\n--- All inputs ---")
    for inp in page.query_selector_all("input"):
        print(" ", inp.get_attribute("type"), inp.get_attribute("name"),
              inp.get_attribute("placeholder"), inp.get_attribute("aria-label"))

    print("\n--- All buttons ---")
    for btn in page.query_selector_all("button"):
        print(" ", btn.inner_text()[:60].strip())

    print("\n--- Tables ---")
    for i, tbl in enumerate(page.query_selector_all("table")):
        headers = [th.inner_text().strip() for th in tbl.query_selector_all("th")]
        rows_count = len(tbl.query_selector_all("tbody tr"))
        print(f"  Table {i}: headers={headers}, rows={rows_count}")

    print(f"\n--- API calls intercepted ({len(api_calls)}) ---")
    for call in api_calls:
        body_preview = json.dumps(call["body"])[:200]
        print(f"  {call['url']}")
        print(f"    {body_preview}")

    browser.close()

print("\nDone.")
