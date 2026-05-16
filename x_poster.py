"""X自動投稿スクリプト（Stealth + Shift+Enter + dispatch_event対応版）"""
import os, json, asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import requests

load_dotenv('/Users/bani/analytics/.env')

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID = "e8f356b4-3d5a-4713-8a4e-b016e49c1d47"
NOTION_HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
ACCOUNTS = {
    "nakyatsukuruapp": {"cookies": json.loads(os.environ.get("X_COOKIES_NAKYATSUKURUAPP", "{}")), "username": "nakyatsukuruapp"},
    "Sirius": {"cookies": json.loads(os.environ.get("X_COOKIES_SIRIUS", "{}")), "username": "sirius_fukugyo"},
}
JST = timezone(timedelta(hours=9))

def get_today_posts(account_name):
    today = datetime.now(JST).strftime("%Y-%m-%d")
    res = requests.post(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query", headers=NOTION_HEADERS, json={
        "filter": {"and": [
            {"property": "アカウント", "select": {"equals": account_name}},
            {"property": "ステータス", "select": {"equals": "ストック中"}},
            {"property": "投稿日", "date": {"equals": today}},
            {"property": "プラットフォーム", "multi_select": {"contains": "X"}},
        ]}
    })
    return res.json().get("results", [])

def should_post_now(page_props):
    rt = page_props.get("投稿時刻", {}).get("rich_text", [])
    if not rt: return True
    time_str = rt[0].get("plain_text", "")
    if not time_str: return True
    try:
        now = datetime.now(JST)
        h, m = map(int, time_str.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return abs((now - target).total_seconds()) <= 1800
    except:
        return True

def mark_posted(page_id):
    requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=NOTION_HEADERS,
        json={"properties": {"ステータス": {"select": {"name": "投稿済み"}}}})

async def type_multiline(page, text):
    for i, line in enumerate(text.split('\n')):
        if i > 0:
            await page.keyboard.press('Shift+Enter')
            await asyncio.sleep(0.15)
        if line:
            await page.keyboard.type(line, delay=40)

async def post_to_x(account_name, text):
    info = ACCOUNTS[account_name]
    cookies, username = info["cookies"], info["username"]
    if not cookies: return False, "クッキーなし"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(**pw.devices["Desktop Chrome"])
        await ctx.add_cookies([{"name":k,"value":str(v),"domain":".x.com","path":"/","secure":True} for k,v in cookies.items()])
        page = await ctx.new_page()
        await Stealth().apply_stealth_async(page)
        try:
            await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            before_arts = await page.query_selector_all('article[data-testid="tweet"]')
            before_text = ""
            if before_arts:
                te = await before_arts[0].query_selector('[data-testid="tweetText"]')
                if te: before_text = (await te.inner_text())[:50]

            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            box = await page.query_selector('[data-testid="tweetTextarea_0"]')
            if not box: return False, "テキストエリアなし"
            await box.click(force=True)
            await asyncio.sleep(1)
            await type_multiline(page, text)
            await asyncio.sleep(2)
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.5)

            btn = await page.query_selector('[data-testid="tweetButtonInline"]') or await page.query_selector('[data-testid="tweetButton"]')
            if not btn: return False, "ボタンなし"
            if not await btn.is_enabled(): return False, "ボタン無効（文字数超過？）"
            await btn.dispatch_event('click')  # layers divをバイパス
            await asyncio.sleep(5)

            await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            after_arts = await page.query_selector_all('article[data-testid="tweet"]')
            after_text = ""
            if after_arts:
                te = await after_arts[0].query_selector('[data-testid="tweetText"]')
                if te: after_text = (await te.inner_text())[:50]

            if before_text != after_text:
                return True, f"確認済み: {after_text[:30]}"
            return False, "post not confirmed"
        except Exception as e:
            return False, str(e)
        finally:
            await browser.close()

async def main():
    now_jst = datetime.now(JST)
    print(f"=== X 自動投稿 {now_jst.strftime('%Y-%m-%d %H:%M')} ===")
    posted = False
    for account_name in ACCOUNTS:
        pages = get_today_posts(account_name)
        for p in pages:
            props = p["properties"]
            if not should_post_now(props): continue
            title = props.get("投稿文", {}).get("title", [])
            text = "".join(t.get("plain_text", "") for t in title)
            if not text: continue
            print(f"\n  [{account_name}] 投稿中...")
            ok, msg = await post_to_x(account_name, text)
            print(f"  X: {'✅' if ok else '❌'} ({msg})")
            if ok:
                mark_posted(p["id"])
            posted = True
    if not posted:
        print("今日の投稿予定はありません")
    print("\n=== 完了 ===")

if __name__ == "__main__":
    asyncio.run(main())
