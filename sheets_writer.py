"""
Google Sheets ライター
シート名ごとにヘッダー管理 → 日付順に行追加
"""

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

SHEET_HEADERS = {
    "X_アカウント": ["date", "account", "followers", "following"],
    "X_ツイート": [
        "date", "account", "tweet_id", "created_at", "text",
        "views", "likes", "retweets", "replies", "quotes", "bookmarks"
    ],
    "Threads_アカウント": ["date", "account", "views", "followers_count", "reach"],
    "Threads_投稿": [
        "date", "account", "post_id", "url", "text", "likes", "replies"
    ],
    "Note_アカウント": ["date", "account", "followers", "following"],
    "Note_記事": ["date", "account", "note_key", "url", "title", "views", "likes"],
}


class SheetsWriter:
    def __init__(self, credentials_json: dict, spreadsheet_id: str):
        creds = Credentials.from_service_account_info(credentials_json, scopes=SCOPES)
        gc = gspread.authorize(creds)
        self._ss = gc.open_by_key(spreadsheet_id)
        self._sheets: dict = {}

    def _get_or_create_sheet(self, sheet_name: str) -> gspread.Worksheet:
        if sheet_name in self._sheets:
            return self._sheets[sheet_name]

        try:
            ws = self._ss.worksheet(sheet_name)
            # ヘッダーが空なら追加
            if ws.row_count == 0 or not ws.row_values(1):
                headers = SHEET_HEADERS.get(sheet_name, [])
                if headers:
                    ws.append_row(headers, value_input_option="RAW")
        except gspread.WorksheetNotFound:
            ws = self._ss.add_worksheet(title=sheet_name, rows=5000, cols=20)
            headers = SHEET_HEADERS.get(sheet_name, [])
            if headers:
                ws.append_row(headers, value_input_option="RAW")

        self._sheets[sheet_name] = ws
        return ws

    def append(self, sheet_name: str, row_data: dict):
        ws = self._get_or_create_sheet(sheet_name)
        headers = SHEET_HEADERS.get(sheet_name, list(row_data.keys()))
        row = [str(row_data.get(h, "")) for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        print(f"    → {sheet_name} に書き込み: {row[:3]}...")

    def append_batch(self, sheet_name: str, rows: list):
        if not rows:
            return
        ws = self._get_or_create_sheet(sheet_name)
        headers = SHEET_HEADERS.get(sheet_name, list(rows[0].keys()))
        matrix = [[str(r.get(h, "")) for h in headers] for r in rows]
        ws.append_rows(matrix, value_input_option="USER_ENTERED")
        print(f"    → {sheet_name} に {len(matrix)} 行書き込み")
