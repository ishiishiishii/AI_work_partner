import re
import time

import httpx
from psycopg import Connection

# customer.location はデモ用の架空住所("茨城県水戸市宮町5-23-7"のような形式)で、
# 都道府県・市区町村・町名は実在するが、末尾の番地(chome-block-number)だけが架空。
# 実在しない番地込みでジオコーディングしても意味が無いため、末尾のこのパターンだけを
# 取り除いてから検索する。
_BLOCK_NUMBER_PATTERN = re.compile(r"\d+-\d+-\d+$")

# 国土地理院(GSI)の住所検索API。無料・登録不要・APIキー不要。
_GSI_ENDPOINT = "https://msearch.gsi.go.jp/address-search/AddressSearch"

# 無料の公共サービスに負荷をかけすぎないよう、バッチ処理では1件ごとにこれだけ間隔を空ける。
_RATE_LIMIT_SECONDS = 0.3

# 1回のバックフィルで処理する最大件数。多すぎるとバックグラウンドタスクが長時間化するため、
# 少しずつ複数回のリクエストにまたがって完了させる(呼び出しごとにこの件数ずつ進む)。
DEFAULT_BACKFILL_LIMIT = 20


def strip_block_number(location: str) -> str:
    """番地部分を除いた、実在する都道府県+市区町村+町名だけを返す。"""
    return _BLOCK_NUMBER_PATTERN.sub("", location).strip()


def geocode_address(address: str) -> tuple[float, float] | None:
    """住所文字列から (緯度, 経度) を返す。該当なし・通信失敗時は None。"""
    try:
        response = httpx.get(_GSI_ENDPOINT, params={"q": address}, timeout=5)
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not results:
        return None
    lng, lat = results[0]["geometry"]["coordinates"]
    return (lat, lng)


def geocode_customer_location(location: str) -> tuple[float, float] | None:
    return geocode_address(strip_block_number(location))


def backfill_customer_coordinates(conn: Connection, *, limit: int = DEFAULT_BACKFILL_LIMIT) -> int:
    """lat/lngが未設定の顧客を最大limit件ジオコーディングしてDBへ保存する。
    未設定のままの顧客はフロント側で従来の都道府県+ランダムズレにフォールバックするので、
    ここで何件処理できてもできなくても、呼び出し元の処理は失敗させない。"""
    rows = conn.execute(
        "select customer_id, location from customer where lat is null order by customer_id limit %s",
        (limit,),
    ).fetchall()
    updated = 0
    for index, row in enumerate(rows):
        coords = geocode_customer_location(row["location"])
        if coords is not None:
            lat, lng = coords
            conn.execute(
                "update customer set lat = %s, lng = %s where customer_id = %s",
                (lat, lng, row["customer_id"]),
            )
            updated += 1
        if index < len(rows) - 1:
            time.sleep(_RATE_LIMIT_SECONDS)
    conn.commit()
    return updated
