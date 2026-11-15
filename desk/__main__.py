import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .models import Brief
from .production import Producer, fingerprint
from .provider import Provider
from .publishing import build_site, export_episode
from .storage import Budget, Store

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Big Sky Fight Desk")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("studio")
    commands.add_parser("build")
    new = commands.add_parser("new")
    new.add_argument("topic")
    new.add_argument("--as-of", required=True)
    new.add_argument("--minutes", type=int, default=4)
    for name in ("draft", "review", "revise", "media", "listen", "approve", "export"):
        commands.add_parser(name).add_argument("episode")
    args = parser.parse_args()
    if args.command == "studio":
        import uvicorn
        from .server import create_app
        uvicorn.run(create_app(), host="127.0.0.1", port=8765)
        return
    if args.command == "build":
        print(build_site(os.getenv("PUBLIC_URL", "https://www.taylordorsett.com/big-sky-fight-desk").rstrip("/")))
        return
    store = Store(ROOT / ".local" / "episodes")
    budget = Budget(ROOT / ".local" / "usage.sqlite", float(os.getenv("DAILY_ALLOWANCE", "2")), float(os.getenv("MONTHLY_ALLOWANCE", "10")))
    producer = Producer(store, budget, Provider)
    if args.command == "new":
        episode = store.create(Brief(topic=args.topic, as_of=args.as_of, minutes=args.minutes))
    elif args.command == "approve":
        episode = store.get(args.episode)
        producer.require_review(episode)
        episode.update(approved=True, approval_hash=fingerprint(episode["script"]))
        store.save(episode)
    elif args.command == "export":
        episode = export_episode(store, args.episode, ROOT / "public")
    else:
        episode = producer.run(args.episode, args.command)
    print(episode["id"])


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
