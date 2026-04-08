"""
Threads クライアント
Playwright でスクレイピング（公式API不要）
"""

import asyncio
import re
from playwright.async_api import async_playwright


class ThreadsClient:
    def __init__(self, cookies: dict, username: str):
        self._cookies = cookies
        self._username = username
        self._browser = None
        self._page = None

    async def init(self):
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=True)
        ctx = await self._browser.new_context()
        # Threads のクッキーをセット
        await ctx.add_cookies([
            {"name": k, "value": v, "domain": ".threads.net", "path": "/"}
            for k, v in self._cookies.items()
        ])
        self._page = await ctx.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()

    async def get_profile(self) -> dict:
        """フォロワー数を取得"""
        await self._page.goto(
            f"https://www.threads.net/@{self._username}",
            wait_until="domcontentloaded"
        )
        await asyncio.sleep(6)

        # スクロールして動的コンテンツを読み込む
        await self._page.evaluate("window.scrollTo(0, 300)")
        await asyncio.sleep(2)

        followers = 0
        try:
            body_text = await self._page.inner_text("body")
            # "フォロワー6人" or "フォロワー1,234人" パターン
            m = re.search(r"フォロワー([\d,]+)人", body_text)
            if not m:
                # 英語表記 "6 followers" パターン
                m = re.search(r"([\d,]+)\s*followers?", body_text, re.IGNORECASE)
            if m:
                followers = int(m.group(1).replace(",", ""))
        except Exception as e:
            print(f"    [WARN] Threads profile error: {e}")

        return {"followers": followers}

    async def get_posts(self, limit: int = 10) -> list[dict]:
        """投稿のいいね数などを取得"""
        await self._page.goto(
            f"https://www.threads.net/@{self._username}",
            wait_until="domcontentloaded"
        )
        await asyncio.sleep(4)

        # スクロールして投稿を読み込む
        for _ in range(2):
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

        posts = []
        try:
            # 投稿リンクを取得
            links = await self._page.query_selector_all(
                f'a[href*="/@{self._username}/post/"]'
            )
            post_urls = []
            seen = set()
            for el in links:
                href = await el.get_attribute("href")
                if href and href not in seen:
                    seen.add(href)
                    url = href if href.startswith("http") else f"https://www.threads.net{href}"
                    post_urls.append(url)
                if len(post_urls) >= limit:
                    break

            for url in post_urls:
                post = await self._get_post_stats(url)
                if post:
                    posts.append(post)
                await asyncio.sleep(1.5)

        except Exception as e:
            print(f"    [WARN] Threads posts error: {e}")

        return posts

    async def _get_post_stats(self, url: str) -> dict | None:
        """投稿単体のいいね・返信数を取得"""
        try:
            await self._page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # post_id を URL から取得
            m = re.search(r"/post/([A-Za-z0-9_-]+)", url)
            post_id = m.group(1) if m else url

            # テキスト
            text = ""
            text_el = await self._page.query_selector('[data-pressable-container="true"] span')
            if text_el:
                text = await text_el.inner_text()

            # いいね数・返信数をページテキストから取得
            likes = replies = 0
            body_text = await self._page.inner_text("body")

            m_likes = re.search(r"([\d,]+)\s*いいね", body_text)
            if m_likes:
                likes = int(m_likes.group(1).replace(",", ""))

            m_replies = re.search(r"([\d,]+)\s*件の返信", body_text)
            if m_replies:
                replies = int(m_replies.group(1).replace(",", ""))

            return {
                "post_id": post_id,
                "url": url,
                "text": text[:100],
                "likes": likes,
                "replies": replies,
            }
        except Exception as e:
            print(f"    [WARN] Threads post error ({url}): {e}")
            return None
