import hashlib
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from desk.models import Brief
from desk.production import Producer, fingerprint, validate_evidence, validate_script
from desk.provider import Provider
from desk.publishing import export_episode
from desk.server import create_app
from desk.storage import Budget, Store

SOURCES = [{"title": "Venue", "url": "https://www.montana.edu/event"},
           {"title": "Results", "url": "https://combatreg.com/event"}]
EVIDENCE = {"summary": "A Montana card", "facts": [
    {"text": "The card was in Montana.", "source_urls": [SOURCES[0]["url"]]},
    {"text": "The card included MMA.", "source_urls": [SOURCES[1]["url"]]}], "uncertainties": []}
SCRIPT = {"title": "Montana report", "description": "A sourced episode", "cover_brief": "Mountains",
          "segments": [{"heading": "Opening", "text": "This is Big Sky Fight Desk. " * 18, "fact_ids": [0]},
                       {"heading": "Card", "text": "The card included MMA. " * 24, "fact_ids": [1]}]}


class FakeProvider:
    calls = []

    def research(self, brief):
        self.calls.append("research")
        return {"text": "The card was in Montana and included MMA.", "sources": SOURCES}

    def evidence(self, research):
        self.calls.append("evidence")
        return copy.deepcopy(EVIDENCE)

    def draft(self, brief, evidence):
        self.calls.append("draft")
        return copy.deepcopy(SCRIPT)

    def review(self, episode):
        self.calls.append("review")
        return {"passed": True, "issues": [], "notes": "Supported"}


@pytest.fixture
def setup(tmp_path):
    FakeProvider.calls = []
    store = Store(tmp_path / "episodes")
    episode = store.create(Brief(topic="A real Montana MMA event", as_of="2026-11-14"))
    budget = Budget(tmp_path / "budget.sqlite")
    producer = Producer(store, budget, FakeProvider)
    return store, episode, budget, producer


def test_completed_draft_resumes_without_new_spend(setup):
    store, episode, budget, producer = setup
    producer.run(episode["id"], "draft")
    first = budget.usage()
    producer.run(episode["id"], "draft")
    assert budget.usage() == first
    assert FakeProvider.calls == ["research", "evidence", "draft", "review"]
    assert (store.folder(episode["id"]) / "transcript.txt").exists()


def test_foreign_source_is_rejected():
    bad = copy.deepcopy(EVIDENCE)
    bad["facts"][0]["source_urls"] = ["https://made-up.example/result"]
    with pytest.raises(ValueError, match="did not retrieve"):
        validate_evidence(bad, {"sources": SOURCES})


@pytest.mark.parametrize("index", [-1, 3])
def test_script_cannot_cite_nonexistent_fact(index):
    bad = copy.deepcopy(SCRIPT)
    bad["segments"][0]["fact_ids"] = [index]
    with pytest.raises(ValueError, match="does not exist"):
        validate_script(bad, EVIDENCE)


def test_failed_review_blocks_media_and_export(setup):
    store, episode, budget, producer = setup
    producer.run(episode["id"], "draft")
    episode = store.get(episode["id"])
    episode["review"] = {"passed": False, "issues": ["Result unsupported"]}
    store.save(episode)
    with pytest.raises(ValueError, match="passing evidence"):
        producer.run(episode["id"], "media")
    with pytest.raises(ValueError, match="passing evidence"):
        export_episode(store, episode["id"], store.root / "public")


def test_edit_invalidates_approval_and_media(setup):
    store, episode, budget, producer = setup
    producer.run(episode["id"], "draft")
    episode = store.get(episode["id"])
    episode.update(approved=True, audio_hash=fingerprint(SCRIPT), cover_hash=fingerprint(SCRIPT))
    store.save(episode)
    script = copy.deepcopy(SCRIPT)
    script["segments"][0]["text"] += " A correction."
    edited = producer.edit(episode["id"], script)
    assert not edited["approved"]
    assert "review" not in edited and "audio_hash" not in edited and "cover_hash" not in edited


def test_export_requires_specific_approval_and_excludes_private_data(setup, tmp_path):
    store, episode, budget, producer = setup
    producer.run(episode["id"], "draft")
    episode = store.get(episode["id"])
    digest = fingerprint(episode["script"])
    episode.update(audio_hash=digest, cover_hash=digest, duration_seconds=180)
    store.save(episode)
    with pytest.raises(ValueError, match="approve"):
        export_episode(store, episode["id"], tmp_path / "public")
    episode.update(approved=True, approval_hash=digest)
    store.save(episode)
    for name in ("episode.mp3", "cover.png"):
        (store.folder(episode["id"]) / name).write_bytes(b"test fixture")
    episode.update(listening_review={"passed": True}, listening_script_hash=digest,
                   listening_audio_hash=hashlib.sha256(b"test fixture").hexdigest())
    store.save(episode)
    result = export_episode(store, episode["id"], tmp_path / "public")
    assert "research" not in result and "log" not in result and "brief" not in result
    assert len(result["sources"]) == 2
    first_date = result["published_at"]
    assert export_episode(store, episode["id"], tmp_path / "public")["published_at"] == first_date


def test_failed_call_still_reserves_budget(setup):
    store, episode, budget, producer = setup
    class Broken(FakeProvider):
        def research(self, brief):
            raise RuntimeError("secret provider details")
    producer.provider_factory = Broken
    with pytest.raises(ValueError):
        producer.run(episode["id"], "draft")
    assert budget.usage()["daily"] == 0.20
    assert "secret" not in store.get(episode["id"])["error"]


def test_concurrent_reservations_cannot_exceed_allowance(tmp_path):
    budget = Budget(tmp_path / "budget.sqlite", daily=0.40)
    def reserve(_):
        try:
            budget.reserve("episode", "research")
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(20))) == 2
    assert budget.usage()["daily"] == .40


def test_monthly_limit_also_applies(tmp_path):
    budget = Budget(tmp_path / "budget.sqlite", daily=2, monthly=.20)
    budget.reserve("episode", "research")
    with pytest.raises(ValueError, match="allowance reached"):
        budget.reserve("episode", "draft")


@pytest.mark.parametrize("url", ["http://combatreg.com/x", "https://combatreg.com.evil.example/x", "https://localhost/x", "file:///etc/passwd", "https://user:password@combatreg.com/x"])
def test_source_domain_boundaries(url):
    assert not Provider.allowed(url)


def test_local_studio_rejects_cross_origin_and_wrong_host(tmp_path):
    app = create_app(tmp_path, FakeProvider)
    with TestClient(app) as client:
        token = client.get("/api/state").json()["token"]
        brief = {"topic": "Montana MMA news", "as_of": "2026-11-14"}
        assert client.post("/api/episodes", json=brief).status_code == 403
        assert client.post("/api/episodes", json=brief, headers={"X-Desk-Token": token, "Origin": "https://evil.example"}).status_code == 403
        assert client.get("/api/state", headers={"Host": "evil.example"}).status_code == 400
        assert client.post("/api/episodes", json=brief, headers={"X-Desk-Token": token}).status_code == 200


def test_paths_cannot_escape_episode_folder(tmp_path):
    with pytest.raises(ValueError):
        Store(tmp_path).folder("../../.env")


def test_stale_media_is_not_served(setup, tmp_path):
    app = create_app(tmp_path / "app", FakeProvider)
    store = app.state.store
    episode = store.create(Brief(topic="Montana MMA report", as_of="2026-11-14"))
    episode.update(script=SCRIPT, audio_hash="old")
    store.save(episode)
    (store.folder(episode["id"]) / "episode.mp3").write_bytes(b"old audio")
    with TestClient(app) as client:
        assert client.get(f"/media/{episode['id']}/episode.mp3").status_code == 404


def test_review_with_issues_cannot_pass(setup):
    store, episode, budget, producer = setup
    class Inconsistent(FakeProvider):
        def review(self, episode):
            return {"passed": True, "issues": ["Wrong event date"], "notes": "Problem"}
    producer.provider_factory = Inconsistent
    result = producer.run(episode["id"], "draft")
    assert not result["review"]["passed"]


def test_audio_check_is_bound_to_recording_and_script(setup):
    store, episode, budget, producer = setup
    producer.run(episode["id"], "draft")
    episode = store.get(episode["id"])
    digest = fingerprint(episode["script"])
    path = store.folder(episode["id"]) / "episode.mp3"
    path.write_bytes(b"recording")
    episode.update(audio_hash=digest, cover_hash=digest)
    store.save(episode)
    class Listener(FakeProvider):
        def listen(self, script, audio_path):
            assert audio_path.read_bytes() == b"recording"
            return {"passed": True, "issues": [], "notes": "Clear", "clarity": 5, "naturalness": 4}
    producer.provider_factory = Listener
    checked = producer.run(episode["id"], "listen")
    producer.require_listening_review(checked)
    path.write_bytes(b"replacement")
    with pytest.raises(ValueError, match="audio review"):
        producer.require_listening_review(checked)


def test_weak_audio_score_cannot_pass(setup):
    store, episode, budget, producer = setup
    producer.run(episode["id"], "draft")
    episode = store.get(episode["id"])
    digest = fingerprint(episode["script"])
    (store.folder(episode["id"]) / "episode.mp3").write_bytes(b"recording")
    episode.update(audio_hash=digest, cover_hash=digest)
    store.save(episode)
    class Listener(FakeProvider):
        def listen(self, script, audio_path):
            return {"passed": True, "issues": [], "notes": "Flat", "clarity": 5, "naturalness": 2}
    producer.provider_factory = Listener
    assert not producer.run(episode["id"], "listen")["listening_review"]["passed"]


def test_database_only_evidence_cannot_start_an_episode():
    url = "https://www.sherdog.com/events/example"
    evidence = copy.deepcopy(EVIDENCE)
    for fact in evidence["facts"]:
        fact["source_urls"] = [url]
    with pytest.raises(ValueError, match="beyond fight databases"):
        validate_evidence(evidence, {"sources": [{"url": url, "excerpt": "Two supported facts"}]})


def test_revision_keeps_disclosure_off_the_spoken_script():
    provider = object.__new__(Provider)
    prompts = []
    provider.structured = lambda schema, prompt: prompts.append(prompt) or SCRIPT
    provider.revise({"brief": {}, "research": {"sources": SOURCES}, "evidence": EVIDENCE,
                     "script": SCRIPT, "review": {"issues": []}})
    assert "Keep AI voice disclosure on the page, not in the spoken script" in prompts[0]
    assert "Include the AI voice disclosure" not in prompts[0]
