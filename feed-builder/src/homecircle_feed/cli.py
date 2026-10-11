"""Command line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from homecircle_feed.http_client import PoliteClient
from homecircle_feed.pipeline import build, load_json
from homecircle_feed.seed import seed_previous

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="homecircle-feed", description="Build the HomeCircle meeting feed.")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build", help="Fetch enabled sources and write dist/")
    build_parser.add_argument("--country", action="append", help="ISO country code. Repeatable. Default: every enabled country.")
    build_parser.add_argument("--output", type=Path, default=ROOT / "dist")
    build_parser.add_argument("--cache", type=Path, default=ROOT / ".cache" / "http")
    build_parser.add_argument("--registry", type=Path, default=ROOT / "sources" / "registry.json")
    build_parser.add_argument("--curated", type=Path, default=ROOT / "curated" / "feed-items.json")
    build_parser.add_argument("--refresh", action="store_true", help="Bypass the 12-hour response cache.")
    build_parser.add_argument("--skip-link-check", action="store_true")
    build_parser.add_argument("--min-interval", type=float, default=1.0, help="Seconds between requests to the same host.")

    show = sub.add_parser("sources", help="Print the source registry, including sources that are not fetched.")
    show.add_argument("--registry", type=Path, default=ROOT / "sources" / "registry.json")

    seed = sub.add_parser("seed", help="Rebuild dist/<cc>/meetings.json from an already published feed folder.")
    seed.add_argument("--from", dest="feed_dir", type=Path, required=True, help="Published folder, e.g. site/feed/au")
    seed.add_argument("--output", type=Path, default=ROOT / "dist")
    seed.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "sources":
        print(json.dumps(load_json(args.registry), indent=2))
        return 0
    if args.command == "seed":
        print(json.dumps(seed_previous(args.feed_dir, args.output, force=args.force)))
        return 0

    registry = load_json(args.registry)
    client = PoliteClient(args.cache, registry["user_agent"], min_interval=args.min_interval)

    def get_json(url: str):
        return client.get_json(url, refresh=args.refresh)

    summary = build(
        registry_path=args.registry,
        curated_path=args.curated,
        output_dir=args.output,
        get_json=get_json,
        countries=args.country,
        check_link_urls=not args.skip_link_check,
        link_cache=args.cache / "link-checks.json",
    )
    for country in summary["countries"]:
        print(
            f"{country['country']}: {country['meeting_count']} meetings "
            f"(+{country['added']} -{country['removed']} ~{country['changed']}) "
            f"broken_links={country['broken_links']}"
        )
        for source in country["sources"]:
            print(f"  {source['status']:8} {source['id']:16} kept={source['kept']} fetched={source['fetched']}")
        for path in country.get("publish_files") or []:
            print(f"  publish {path}")
    items = summary["feed_items"]
    print(f"feed items published={items['item_count']} withheld_unapproved={items['withheld_unapproved']}")
    return 0
