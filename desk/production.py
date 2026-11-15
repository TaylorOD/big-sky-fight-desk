import hashlib
import json
import threading
from pathlib import Path

from mutagen.mp3 import MP3
from PIL import Image

from .models import Evidence, Script
from .storage import now


def fingerprint(script):
    return hashlib.sha256(json.dumps(script, sort_keys=True).encode()).hexdigest()


def validate_evidence(evidence, research):
    evidence = Evidence.model_validate(evidence)
    known = {s["url"] for s in research["sources"] if s.get("excerpt", True)}
    if not 2 <= len(evidence.facts) <= 24:
        raise ValueError("Need 2 to 24 sourced facts before drafting.")
    for fact in evidence.facts:
        if not fact.source_urls or any(url not in known for url in fact.source_urls):
            raise ValueError("A fact refers to a source that research did not retrieve.")
    return evidence.model_dump()


def validate_script(script, evidence):
    script = Script.model_validate(script)
    text = script.spoken()
    if not 150 <= len(text.split()) <= 750 or len(text) > 6000:
        raise ValueError("The script needs 150 to 750 words and at most 6000 characters. Edit or draft again.")
    if len(script.title) > 140 or len(script.description) > 600:
        raise ValueError("Shorten the episode title or description.")
    if not 2 <= len(script.segments) <= 8:
        raise ValueError("Use 2 to 8 script segments.")
    if not any(s.fact_ids for s in script.segments):
        raise ValueError("The script has no fact references.")
    for segment in script.segments:
        if any(index < 0 or index >= len(evidence["facts"]) for index in segment.fact_ids):
            raise ValueError("The script points to a fact that does not exist.")
    return script.model_dump()


class Producer:
    def __init__(self, store, budget, provider_factory):
        self.store, self.budget, self.provider_factory = store, budget, provider_factory
        self.lock = threading.Lock()
        self.busy = None

    def run(self, episode_id, action):
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another operation is running. Let it finish first.")
        self.busy = episode_id
        episode = None
        try:
            episode = self.store.get(episode_id)
            episode["error"] = None
            self.store.save(episode)
            provider = self.provider_factory()

            def call(operation, function):
                self.budget.reserve(episode_id, operation)
                episode["status"] = operation
                episode["log"].append({"at": now(), "step": operation})
                self.store.save(episode)
                return function()

            if action == "draft":
                if not episode.get("research"):
                    episode["research"] = call("research", lambda: provider.research(episode["brief"]))
                    episode["researched_at"] = now()
                    self.store.save(episode)
                if not episode.get("evidence"):
                    evidence = call("evidence", lambda: provider.evidence(episode["research"]))
                    episode["evidence"] = validate_evidence(evidence, episode["research"])
                    self.store.save(episode)
                if not episode.get("script"):
                    script = call("draft", lambda: provider.draft(episode["brief"], episode["evidence"]))
                    episode["script"] = validate_script(script, episode["evidence"])
                    self.save_script(episode)
                if not episode.get("review"):
                    self.check(episode, provider, call)
            elif action == "review":
                if not episode.get("script"):
                    raise ValueError("Draft a script first.")
                self.check(episode, provider, call)
            elif action == "revise":
                if not episode.get("script") or not episode.get("review"):
                    raise ValueError("Draft and check a script first.")
                script = call("draft", lambda: provider.revise(episode))
                episode["script"] = validate_script(script, episode["evidence"])
                episode["approved"] = False
                for key in ("audio_hash", "cover_hash", "duration_seconds"):
                    episode.pop(key, None)
                self.save_script(episode)
                self.check(episode, provider, call)
            elif action == "media":
                self.require_review(episode)
                folder = self.store.folder(episode_id)
                for operation, filename in (("audio", "episode.mp3"), ("cover", "cover.png")):
                    if episode.get(operation + "_hash") == fingerprint(episode["script"]) and (folder / filename).exists():
                        continue
                    temp = folder / ("working-" + filename)
                    call(operation, lambda op=operation, dest=temp: getattr(provider, op)(episode["script"], dest))
                    if operation == "audio":
                        duration = MP3(temp).info.length
                        if not 30 < duration < 600:
                            raise ValueError("Audio duration is outside the expected range.")
                        episode["duration_seconds"] = round(duration)
                    else:
                        with Image.open(temp) as img:
                            if img.format != "PNG" or img.width < 512 or img.height < 512:
                                raise ValueError("The cover is not a valid PNG.")
                            img.verify()
                    temp.replace(folder / filename)
                    episode[operation + "_hash"] = fingerprint(episode["script"])
                    self.store.save(episode)
            else:
                raise ValueError("Unknown production action.")
            episode["status"] = "ready" if self.media_ready(episode) else "reviewed" if episode.get("review", {}).get("passed") else "needs review"
            self.store.save(episode)
            return episode
        except Exception as exc:
            if episode:
                # Do not write provider response bodies, request headers or credentials to logs.
                message = str(exc) if isinstance(exc, ValueError) else self.friendly_error(exc)
                episode.update(status="paused", error=message)
                self.store.save(episode)
            raise ValueError(episode["error"] if episode else "Episode not found.") from None
        finally:
            self.busy = None
            self.lock.release()

    @staticmethod
    def friendly_error(exc):
        code = getattr(exc, "status_code", None)
        if code == 401:
            return "OpenAI rejected the API key. Check your local .env file."
        if code == 403:
            return "OpenAI denied this model. Image generation may require organization verification. Your other files are saved."
        if code == 429:
            return "OpenAI reached a usage or credit limit. Check your account, then resume."
        if code == 400:
            return "OpenAI rejected this request. Check model access and the configured SDK version. Your work is saved."
        return "Generation stopped before finishing. Check your connection and API setup, then resume. Your work is saved."

    def check(self, episode, provider, call):
        episode["approved"] = False
        result = call("review", lambda: provider.review(episode))
        result["passed"] = bool(result["passed"] and not result["issues"])
        episode["review"] = result
        episode["review_hash"] = fingerprint(episode["script"])
        self.store.save(episode)

    def save_script(self, episode):
        folder = self.store.folder(episode["id"])
        (folder / "transcript.txt").write_text(Script.model_validate(episode["script"]).spoken() + "\n", encoding="utf-8")
        self.store.save(episode)

    def edit(self, episode_id, script):
        with self.lock:
            episode = self.store.get(episode_id)
            episode["script"] = validate_script(script, episode["evidence"])
            for key in ("review", "review_hash", "audio_hash", "cover_hash", "duration_seconds"):
                episode.pop(key, None)
            episode.update(approved=False, status="needs review", error=None)
            self.save_script(episode)
            return episode

    @staticmethod
    def require_review(episode):
        if not episode.get("review", {}).get("passed") or episode.get("review_hash") != fingerprint(episode.get("script")):
            raise ValueError("The current script needs a passing evidence check first.")

    @staticmethod
    def media_ready(episode):
        digest = fingerprint(episode.get("script"))
        return episode.get("audio_hash") == digest and episode.get("cover_hash") == digest
