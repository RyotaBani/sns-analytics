"""
Notion ライター
毎日のフォロワー数をNotionページの「📊 フォロワー数」テーブルに更新する
"""

import os
import json
import requests
from datetime import date


NOTION_PAGE_ID = "32d062e16fa681a2854ff5ab42a21492"
NOTION_API = "https://api.notion.com/v1"


class NotionWriter:
    def __init__(self):
        self.token = os.environ.get("NOTION_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def get_page_blocks(self, page_id: str) -> list:
        """ページのブロック一覧を取得"""
        url = f"{NOTION_API}/blocks/{page_id}/children"
        res = requests.get(url, headers=self.headers)
        res.raise_for_status()
        return res.json().get("results", [])

    def find_table_block(self, page_id: str) -> str | None:
        """📊 フォロワー数テーブルのブロックIDを探す"""
        blocks = self.get_page_blocks(page_id)
        
        # heading の後にあるテーブルを探す
        found_heading = False
        for block in blocks:
            btype = block.get("type", "")
            
            # heading でフォロワー数セクションを検出
            if btype in ("heading_2", "heading_3"):
                text = ""
                for t in block[btype].get("rich_text", []):
                    text += t.get("plain_text", "")
                if "フォロワー" in text:
                    found_heading = True
                    continue
            
            # heading 直後のテーブルを返す
            if found_heading and btype == "table":
                return block["id"]
            
            # 別のセクションに入ったらリセット
            if found_heading and btype in ("heading_2", "heading_3", "divider"):
                found_heading = False

        return None

    def get_table_rows(self, table_block_id: str) -> list:
        """テーブルの行を取得"""
        url = f"{NOTION_API}/blocks/{table_block_id}/children"
        res = requests.get(url, headers=self.headers)
        res.raise_for_status()
        return res.json().get("results", [])

    def make_cell(self, text: str) -> list:
        """テーブルセルのrich_textを作成"""
        return [{"type": "text", "text": {"content": str(text)}}]

    def update_row(self, row_block_id: str, cells: list[str]):
        """テーブルの行を更新"""
        url = f"{NOTION_API}/blocks/{row_block_id}"
        data = {
            "table_row": {
                "cells": [self.make_cell(c) for c in cells]
            }
        }
        res = requests.patch(url, headers=self.headers, json=data)
        res.raise_for_status()

    def update_followers(self, followers: dict):
        """
        followers = {
            "nakyatsukuruapp_x": 53,
            "nakyatsukuruapp_threads": 6,
            "sirius_x": 27,
            "sirius_threads": 2,
        }
        """
        if not self.token:
            print("  [WARN] NOTION_TOKEN が設定されていません")
            return

        table_id = self.find_table_block(NOTION_PAGE_ID)
        if not table_id:
            print("  [WARN] Notionのフォロワー数テーブルが見つかりません")
            return

        rows = self.get_table_rows(table_id)
        today = date.today().strftime("%Y/%m/%d")

        # 行マッピング（ヘッダー除く）
        account_map = {
            "nakyatsukuruapp X": followers.get("nakyatsukuruapp_x", "-"),
            "nakyatsukuruapp Threads": followers.get("nakyatsukuruapp_threads", "-"),
            "Sirius X": followers.get("sirius_x", "-"),
            "Sirius Threads": followers.get("sirius_threads", "-"),
        }

        for row in rows[1:]:  # ヘッダー行をスキップ
            cells = row.get("table_row", {}).get("cells", [])
            if not cells:
                continue

            # 現在のアカウント名を取得
            account_name = ""
            for t in cells[0]:
                account_name += t.get("plain_text", "")

            if account_name in account_map:
                # 先週の値 = 今週の値
                prev_value = cells[1][0].get("plain_text", "-") if cells[1] else "-"
                new_value = str(account_map[account_name])

                # 増加数を計算
                try:
                    diff = int(new_value) - int(prev_value)
                    diff_str = f"+{diff}" if diff >= 0 else str(diff)
                except (ValueError, TypeError):
                    diff_str = "-"

                self.update_row(row["id"], [account_name, new_value, prev_value, diff_str])
                print(f"  Notion更新: {account_name} → {new_value}（先週: {prev_value}, 増加: {diff_str}）")

        print(f"  Notion フォロワー数テーブル更新完了 ({today})")
