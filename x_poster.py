"""
X 自動投稿スクリプト - Playwright版（時刻指定対応）
Notionのストックから今日の投稿日 + 投稿時刻が現在時刻±30分のものを取得して投稿
"""

import os
import json
import asyncio
import requests
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

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
    "nakyatsukuruapp": json.loads(os.environ.get("X_COOKIES_NAKYATSUKURUAPP", "{}")),
    "sirius": json.loads(os.environ.get("X_COOKIES_SIRIUS", "{}")),
}

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


def is_within_window(post_time_str, window_minutes=30):
    """投稿時刻が現在時刻の±window分以内かチェック"""
    if not post_time_str:
        return True  # 時刻未設定なら常に投稿
    try:
        now = datetime.now(JST)
        h, m = map(int, post_time_str.strip().split(":"))
        post_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now - post_time).total_seconds() / 60)
        return diff <= window_minutes
    except Exception:
        return True


def get_today_posts():
    today = date.today().strftime("%Y-%m-%d")
    query = {
        "filter": {
            "and": [
                {"property": "投稿日", "date": {"equals": today}},
                {"property": "ステータス", "select": {"equals": "ストック中"}},
                {"property": "プラットフォーム", "multi_select": {"contains": "X"}},
            ]
        }
    }
    res = requests.post(
        f"{NOTION_API}/databases/{NOTION_DB_ID}/query",
        headers=NOTION_HEADERS,
        json=query,
    )
    res.raise_for_status()
    return res.json().get("results", [])


def get_text(page):
    props = page.get("properties", {})
    rich_text = props.get("投稿文", {}).get("title", [])
    return "".join(t.get("plain_text", "") for t in rich_text)


def get_post_time(page):
    props = page.get("properties", {})
    rich_text = props.get("投稿時刻", {}).get("rich_text", [])
    return rich_text[0].get("plain_text", "") if rich_text else ""


def get_account(page):
    props = page.get("properties", {})
    select = props.get("アカウント", {}).get("select", {})
    name = select.get("name", "") if select else ""
    return "sirius" if "sirius" in name.lower() else "nakyatsukuruapp"


def mark_as_posted(page_id):
    requests.patch(
        f"{NOTION_API}/pages/{page_id}",
        headers=NOTION_HEADERS,
        json={"properties": {"ステータス": {"select": {"name": "投稿済み"}}}},
    )


async def post_to_x(account_key, text):
    cookies = ACCOUNT_COOKIES.get(account_key, {})
    if not cookies:
        print(f"  [SKIP] {account_key}: クッキーが未設定")
        return None

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        ctx = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800}
        )
        await ctx.add_cookies([
            {"name": k, "value": str(v), "domain": ".x.com", "path": "/", "secure": True}
            for k, v in cookies.items()
        ])
        page = await ctx.new_page()

        try:
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            tweet_box = await page.query_selector('[data-testid="tweetTextarea_0"]')
            if not tweet_box:
                tweet_box = await page.query_selector('div[role="textbox"]')
            if not tweet_box:
                print(f"  [ERROR] 投稿ボックスが見つかりません")
                return None

            await tweet_box.click(force=True)
            await asyncio.sleep(1)
            await page.keyboard.type(text)
            await asyncio.sleep(1)

            send_btn = await page.query_selector('[data-testid="tweetButtonInline"]')
            if not send_btn:
                send_btn = await page.query_selector('[data-testid="tweetButton"]')
            if not send_btn:
                print(f"  [ERROR] 投稿ボタンが見つかりません")
                return None

            await send_btn.click()
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
    print(f"=== X 自動投稿 {date.today()} {now} ===")
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
            print(f"  [SKIP] 投稿文が空です")
            continue

        if not is_within_window(post_time):
            print(f"  [SKIP] 投稿時刻 {post_time} はまだです（現在 {now}）")
            continue

        print(f"\n--- {account} ---")
        print(f"  投稿時刻: {post_time or '指定なし'}")
        print(f"  投稿文: {text[:50]}...")

        result = await post_to_x(account, text)
        if result:
            mark_as_posted(page_id)

    print("\n=== 完了 ===")


if __name__ == "__main__":
    asyncio.run(main())
