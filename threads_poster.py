"""
Threads 自動投稿スクリプト - Playwright版（時刻指定対応）
"""

import os
import json
import asyncio
import requests
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv('/Users/bani/analytics/.env')

JST = timezone(timedelta(hours=9))
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID = "e8f356b4-3d5a-4713-8a4e-b016e49c1d47"
NOTION_API = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
ACCOUNT_COOKIES = {
    "nakyatsukuruapp": json.loads(os.environ.get("THREADS_COOKIES_NAKYATSUKURUAPP", "{}")),
    "sirius": json.loads(os.environ.get("THREADS_COOKIES_SIRIUS", "{}")),
}
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


def is_within_window(post_time_str, window_minutes=30):
    if not post_time_str:
        return True
    try:
        now = datetime.now(JST)
        h, m = map(int, post_time_str.strip().split(":"))
        post_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return abs((now - post_time).total_seconds() / 60) <= window_minutes
    except Exception:
        return True


def get_today_posts():
    today = date.today().strftime("%Y-%m-%d")
    res = requests.post(
        f"{NOTION_API}/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={"filter": {"and": [
            {"property": "投稿日", "date": {"equals": today}},
            {"property": "ステータス", "select": {"equals": "ストック中"}},
            {"property": "プラットフォーム", "multi_select": {"contains": "Threads"}},
        ]}}
    )
    res.raise_for_status()
    return res.json().get("results", [])


def get_text(page):
    return "".join(t.get("plain_text", "") for t in page["properties"]["投稿文"]["title"])


def get_post_time(page):
    rt = page["properties"].get("投稿時刻", {}).get("rich_text", [])
    return rt[0].get("plain_text", "") if rt else ""


def get_account(page):
    sel = page["properties"].get("アカウント", {}).get("select", {})
    name = sel.get("name", "") if sel else ""
    return "sirius" if "sirius" in name.lower() else "nakyatsukuruapp"


def mark_as_posted(page_id):
    requests.patch(
        f"{NOTION_API}/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={"properties": {"ステータス": {"select": {"name": "投稿済み"}}}},
    )


async def post_to_threads(account_key, text):
    cookies = ACCOUNT_COOKIES.get(account_key, {})
    if not cookies:
        print(f"  [SKIP] {account_key}: クッキーが未設定")
        return None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800})
        cookie_list = []
        for k, v in cookies.items():
            for d in [".threads.net", ".threads.com"]:
                cookie_list.append({"name": k, "value": str(v), "domain": d, "path": "/", "secure": True})
        await ctx.add_cookies(cookie_list)
        page = await ctx.new_page()

        try:
            await page.goto("https://www.threads.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(6)

            # 「What's new?」または「今なにしてる？」をクリック
            for el in await page.query_selector_all('[role="button"]'):
                try:
                    txt = await el.inner_text()
                    if "What's new" in txt or "今なにしてる" in txt:
                        await el.click()
                        print(f"  [OK] 投稿エリアクリック: {txt[:20]}")
                        break
                except Exception:
                    continue

            # wait_for_selectorでcontenteditable出現を待つ（最大10秒）
            try:
                await page.wait_for_selector('[contenteditable="true"]', timeout=10000)
            except Exception:
                print(f"  [ERROR] 入力エリアが出現しませんでした")
                return None

            textarea = await page.query_selector('[contenteditable="true"][role="textbox"]')
            if not textarea:
                textarea = await page.query_selector('[contenteditable="true"]')
            if not textarea:
                print(f"  [ERROR] 入力エリアが見つかりません")
                return None

            await textarea.click(force=True)
            await asyncio.sleep(1)
            await page.keyboard.type(text)
            await asyncio.sleep(1)

            # 「投稿」または「Post」ボタンを探す
            post_btn = None
            for btn in await page.query_selector_all('[role="button"]'):
                try:
                    if (await btn.inner_text()).strip() in ("投稿", "Post"):
                        post_btn = btn
                        break
                except Exception:
                    continue

            if not post_btn:
                print(f"  [ERROR] 投稿ボタンが見つかりません")
                return None

            await post_btn.click(force=True)
            await asyncio.sleep(3)
            print(f"  ✅ 投稿成功（@{account_key}）")
            return True

        except Exception as e:
            print(f"  [ERROR] 投稿失敗: {e}")
            return None
        finally:
            await browser.close()


async def main():
    now = datetime.now(JST).strftime("%H:%M")
    print(f"=== Threads 自動投稿 {date.today()} {now} ===")
    posts = get_today_posts()
    if not posts:
        print("今日の投稿予定はありません")
        return
    for page in posts:
        page_id = page["id"]
        account = get_account(page)
        text = get_text(page)
        post_time = get_post_time(page)
        if not text:
            continue
        if not is_within_window(post_time):
            print(f"  [SKIP] 投稿時刻 {post_time} はまだです（現在 {now}）")
            continue
        print(f"\n--- {account} ---")
        print(f"  投稿時刻: {post_time or '指定なし'}")
        print(f"  投稿文: {text[:50]}...")
        result = await post_to_threads(account, text)
        if result:
            mark_as_posted(page_id)
    print("\n=== 完了 ===")


if __name__ == "__main__":
    asyncio.run(main())
