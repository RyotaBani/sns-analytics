"""
Note.com スクレイパー
Playwright でログイン → 記事一覧・フォロワー数を取得
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright, Page


NOTE_BASE = "https://note.com"


class NoteClient:
    def __init__(self, cookies: dict):
        self._cookies = cookies
        self._browser = None
        self._page: Page = None

    async def init(self):
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=True)
        ctx = await self._browser.new_context()
        await ctx.add_cookies([
            {"name": k, "value": v, "domain": ".note.com", "path": "/"}
            for k, v in self._cookies.items()
        ])
        self._page = await ctx.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()

    async def get_profile(self, username: str) -> dict:
        """フォロワー数・フォロー数を取得"""
        await self._page.goto(
            f"{NOTE_BASE}/{username}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)

        followers = 0
        following = 0
        try:
            follower_el = await self._page.query_selector('a[href*="followers"]')
            if follower_el:
                text = await follower_el.inner_text()
                followers = int(re.sub(r"[^\d]", "", text) or "0")

            following_el = await self._page.query_selector('a[href*="followings"]')
            if following_el:
                text = await following_el.inner_text()
                following = int(re.sub(r"[^\d]", "", text) or "0")
        except Exception:
            pass

        return {"followers": followers, "following": following}

    async def get_articles(self, username: str, limit: int = 20) -> list[dict]:
        """記事一覧ページから記事URLを収集し、各記事のビュー数・スキ数を取得"""
        await self._page.goto(
            f"{NOTE_BASE}/{username}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)

        # スクロールして記事を読み込む
        for _ in range(3):
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

        # 記事リンクを収集（重複除去）
        links = await self._page.query_selector_all("a")
        article_urls = []
        seen = set()
        for el in links:
            href = await el.get_attribute("href")
            if href and f"/{username}/n/" in href:
                url = href if href.startswith("http") else f"{NOTE_BASE}{href}"
                if url not in seen:
                    seen.add(url)
                    article_urls.append(url)
            if len(article_urls) >= limit:
                break

        articles = []
        for url in article_urls:
            article = await self._get_article_stats(url)
            if article:
                articles.append(article)
            await asyncio.sleep(1.5)

        return articles

    async def _get_article_stats(self, article_url: str) -> dict | None:
        """記事ページからビュー・スキを取得"""
        try:
            await self._page.goto(article_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            note_id_match = re.search(r"/n/(n[a-zA-Z0-9]+)", article_url)
            if not note_id_match:
                return None
            note_key = note_id_match.group(1)

            # タイトル
            title = ""
            title_el = await self._page.query_selector("h1")
            if title_el:
                title = await title_el.inner_text()

            # スキ数
            likes = 0
            like_els = await self._page.query_selector_all('[class*="like"], [class*="Like"]')
            for el in like_els:
                text = await el.inner_text()
                nums = re.findall(r"\d+", text)
                if nums:
                    likes = int(nums[0])
                    break

            # 内部APIでビュー数取得
            views = 0
            try:
                api_url = f"https://note.com/api/v2/stats/note/{note_key}"
                resp = await self._page.request.get(api_url)
                if resp.ok:
                    data = await resp.json()
                    views = data.get("data", {}).get("view", 0)
            except Exception:
                pass

            return {
                "note_key": note_key,
                "url": article_url,
                "title": title[:100],
                "views": views,
                "likes": likes,
            }

        except Exception as e:
            print(f"    [WARN] note article error ({article_url}): {e}")
            return None
