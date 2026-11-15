import json
import shutil
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from .production import Producer, fingerprint
from .storage import now, write_json

ROOT = Path(__file__).resolve().parents[1]


def export_episode(store, episode_id, public_dir):
    episode = store.get(episode_id)
    Producer.require_review(episode)
    if not episode.get("approved") or episode.get("approval_hash") != fingerprint(episode["script"]):
        raise ValueError("Review the script and sources, then approve this version before exporting.")
    if not Producer.media_ready(episode):
        raise ValueError("Generate the current audio and cover before exporting.")
    Producer(store, None, None).require_listening_review(episode)
    origin = store.folder(episode_id)
    for name in ("episode.mp3", "cover.png", "transcript.txt"):
        if not (origin / name).is_file():
            raise ValueError("An episode file is missing. Generate media again.")
    target = public_dir / "episodes" / episode_id
    target.mkdir(parents=True, exist_ok=True)
    for name in ("episode.mp3", "cover.png", "transcript.txt"):
        shutil.copyfile(origin / name, target / name)
    facts = episode["evidence"]["facts"]
    used = {url for segment in episode["script"]["segments"] for index in segment["fact_ids"] for url in facts[index]["source_urls"]}
    public = {"id": episode_id, "published_at": episode.get("published_at") or now(),
              "as_of": episode["brief"]["as_of"], "researched_at": episode["researched_at"],
              "title": episode["script"]["title"], "description": episode["script"]["description"],
              "segments": episode["script"]["segments"], "duration_seconds": episode["duration_seconds"],
              "sources": [{"title": s["title"], "url": s["url"]} for s in episode["research"]["sources"] if s["url"] in used],
              "uncertainties": episode["evidence"]["uncertainties"],
              "audio": f"episodes/{episode_id}/episode.mp3", "cover": f"episodes/{episode_id}/cover.png",
              "transcript": f"episodes/{episode_id}/transcript.txt"}
    write_json(target / "episode.json", public)
    episodes = [json.loads(path.read_text(encoding="utf-8")) for path in (public_dir / "episodes").glob("*/episode.json")]
    write_json(public_dir / "episodes.json", sorted(episodes, key=lambda e: e["published_at"], reverse=True))
    episode.update(published_at=public["published_at"], exported_at=now())
    store.save(episode)
    return public


def build_site(base_url, public_dir=None, output=None):
    public_dir = public_dir or ROOT / "public"
    output = output or ROOT / "dist"
    if urlsplit(base_url).scheme != "https" or not urlsplit(base_url).hostname:
        raise ValueError("PUBLIC_URL must be an absolute HTTPS URL.")
    # Only write to the selected output, never remove an arbitrary directory.
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(public_dir, output, dirs_exist_ok=True)
    shutil.copytree(ROOT / "web" / "shared", output / "assets", dirs_exist_ok=True)
    (output / ".nojekyll").touch()
    episodes = json.loads((output / "episodes.json").read_text(encoding="utf-8"))
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, value in {"title": "Big Sky Fight Desk", "link": base_url + "/", "language": "en-us",
                       "description": "Real Montana MMA. Independent reporting with linked sources and an AI generated voice."}.items():
        ET.SubElement(channel, tag).text = value
    for episode in episodes:
        item = ET.SubElement(channel, "item")
        for tag, value in {"title": episode["title"], "description": episode["description"],
                           "link": base_url + "/#episode=" + episode["id"], "guid": base_url + "/#episode=" + episode["id"],
                           "pubDate": format_datetime(datetime.fromisoformat(episode["published_at"]))}.items():
            ET.SubElement(item, tag).text = value
        ET.SubElement(item, "enclosure", url=base_url + "/" + episode["audio"],
                      length=str((output / episode["audio"]).stat().st_size), type="audio/mpeg")
    ET.indent(rss)
    ET.ElementTree(rss).write(output / "feed.xml", encoding="utf-8", xml_declaration=True)
    return output
