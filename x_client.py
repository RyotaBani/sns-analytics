"""
X (Twitter) クライアント - Playwright スクレイピング版
Render (Linux headless) 環境でのbot検知を回避する改善版
"""

import asyncio
import json
import re
import os
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

# bot検知を回避するためのUser-Agent（一般的なChrome）
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class XClient:
    def __init__(self, cookies: dict):
        self.cookies = cookies
        self.username = None

    async def _make_page(self, playwright):
        """ブラウザページを作成（bot検知回避設定付き）"""
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            extra_http_headers={
                "Accept-Language": "ja,en;q=0.9",
            },
        )
        # WebDriver フラグを隠す
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # クッキーをセット
        cookie_list = []
        domain_map = {
            "auth_token": ".x.com",
            "ct0": ".x.com",
            "twid": ".x.com",
            "kdt": ".x.com",
        }
        for name, value in self.cookies.items():
            cookie_list.append({
                "name": name,
                "value": str(value),
                "domain": domain_map.get(name, ".x.com"),
                "path": "/",
                "secure": True,
            })
        await context.add_cookies(cookie_list)

        page = await context.new_page()
        return browser, context, page

    async def get_profile(self, username: str) -> dict:
        """プロフィールページからフォロワー数を取得"""
        async with async_playwright() as pw:
            browser, context, page = await self._make_page(pw)
            try:
                await page.goto(
                    f"https://x.com/{username}",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                # ページが十分読み込まれるまで待つ
                await asyncio.sleep(5)

                followers = 0

                # 方法1: verified_followers リンクのテキストから取得
                try:
                    el = await page.query_selector(f'a[href*="/{username}/verified_followers"]')
                    if not el:
                        el = await page.query_selector(f'a[href*="/followers"]')
                    if el:
                        text = await el.inner_text()
                        m = re.search(r'([\d,]+(?:\.\d+)?[万KMkm]?)\s*(フォロワー|Followers?)', text, re.IGNORECASE)
                        if m:
                            followers = _parse_count(m.group(1))
                except Exception:
                    pass

                # 方法2: ページ全体のテキストからregexで抽出
                if followers == 0:
                    try:
                        content = await page.content()
                        # "53 フォロワー" or "53 Followers" パターン
                        patterns = [
                            r'"followers_count":(\d+)',
                            r'([\d,]+)\s*フォロワー',
                            r'([\d,]+)\s*Followers',
                        ]
                        for pat in patterns:
                            m = re.search(pat, content)
                            if m:
                                followers = _parse_count(m.group(1))
                                if followers > 0:
                                    break
                    except Exception:
                        pass

                # 方法3: aria-label からフォロワー数を探す
                if followers == 0:
                    try:
                        elements = await page.query_selector_all('[aria-label]')
                        for el in elements:
                            label = await el.get_attribute('aria-label') or ""
                            m = re.search(r'([\d,]+)\s*(フォロワー|Followers?)', label, re.IGNORECASE)
                            if m:
                                followers = _parse_count(m.group(1))
                                if followers > 0:
                                    break
                    except Exception:
                        pass

                return {"followers": followers}

            finally:
                await browser.close()

    async def get_recent_tweets(self, username: str, limit: int = 10) -> list:
        """最近のツイートとメトリクスを取得"""
        async with async_playwright() as pw:
            browser, context, page = await self._make_page(pw)
            try:
                await page.goto(
                    f"https://x.com/{username}",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(5)

                tweets = []
                today = datetime.now(JST).strftime("%Y-%m-%d")

                # ツイート要素を取得
                articles = await page.query_selector_all('article[data-testid="tweet"]')

                for article in articles[:limit]:
                    try:
                        # テキスト
                        text_el = await article.query_selector('[data-testid="tweetText"]')
                        text = await text_el.inner_text() if text_el else ""

                        # いいね数
                        like_el = await article.query_selector('[data-testid="like"] span')
                        likes = _parse_count(await like_el.inner_text() if like_el else "0")

                        # リツイート数
                        rt_el = await article.query_selector('[data-testid="retweet"] span')
                        retweets = _parse_count(await rt_el.inner_text() if rt_el else "0")

                        # 返信数
                        reply_el = await article.query_selector('[data-testid="reply"] span')
                        replies = _parse_count(await reply_el.inner_text() if reply_el else "0")

                        # ビュー数（アナリティクス）
                        views = 0
                        view_el = await article.query_selector('a[href*="/analytics"] span')
                        if view_el:
                            views = _parse_count(await view_el.inner_text())

                        if text:
                            tweets.append({
                                "date": today,
                                "account": username,
                                "text": text[:100],
                                "views": views,
                                "likes": likes,
                                "retweets": retweets,
                                "replies": replies,
                            })
                    except Exception:
                        continue

                return tweets

            finally:
                await browser.close()


def _parse_count(text: str) -> int:
    """'1.2万' '53' '1,234' などをintに変換"""
    if not text:
        return 0
    text = text.strip().replace(",", "")
    try:
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        if text.upper().endswith("K"):
            return int(float(text[:-1]) * 1000)
        if text.upper().endswith("M"):
            return int(float(text[:-1]) * 1000000)
        return int(float(text))
    except (ValueError, TypeError):
        return 0
