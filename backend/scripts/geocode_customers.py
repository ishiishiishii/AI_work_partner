import argparse

from app.db import close_pool, get_connection, init_pool
from app.services.geocoding import geocode_pending_customers


def main() -> None:
    parser = argparse.ArgumentParser(
        description="未変換の顧客住所をGeocoding APIで一括座標化します。"
    )
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    if not 1 <= args.limit <= 300:
        parser.error("--limit must be between 1 and 300")

    init_pool()
    try:
        with get_connection() as conn:
            counts = geocode_pending_customers(conn, limit=args.limit)
        print(
            "processed={processed} success={success} review={review} failed={failed}".format(
                **counts
            )
        )
    finally:
        close_pool()


if __name__ == "__main__":
    main()
