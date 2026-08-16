"""Live retrieval and search fail closed to epistemic: unresolved."""

import httpx

from ally.clinical import ClinicalTrialsGov, OpenFdaLabel, PrimaryRegulatoryRetriever
from ally.enums import EpistemicStatus
from ally.retrieval import RetrievalQuery
from ally.web import DuckDuckGoSearcher, HttpFetcher


def test_clinicaltrials_timeout_is_unresolved(monkeypatch):
    monkeypatch.setattr(
        "ally.clinical.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("boom")),
    )
    envelopes = ClinicalTrialsGov().fetch(
        RetrievalQuery(brand_id="exampletide", task="approval", nct_id="NCT05668715")
    )
    assert len(envelopes) == 1
    assert envelopes[0].epistemic is EpistemicStatus.UNRESOLVED
    assert "unresolved" in envelopes[0].text


def test_openfda_malformed_payload_is_unresolved(monkeypatch):
    def fake_get(*args, **kwargs):
        request = httpx.Request("GET", "https://api.fda.gov/drug/label.json")
        return httpx.Response(200, text="[1, 2, 3]", request=request)

    monkeypatch.setattr("ally.clinical.httpx.get", fake_get)
    envelopes = OpenFdaLabel().fetch(
        RetrievalQuery(brand_id="exampletide", task="approval")
    )
    assert envelopes[0].epistemic is EpistemicStatus.UNRESOLVED
    assert "malformed" in envelopes[0].text or "unresolved" in envelopes[0].text


def test_primary_retriever_does_not_crash_on_timeout(monkeypatch):
    monkeypatch.setattr(
        "ally.clinical.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("boom")),
    )
    envelopes = PrimaryRegulatoryRetriever().fetch(
        RetrievalQuery(brand_id="exampletide", task="approval", nct_id="NCT1")
    )
    assert envelopes
    assert all(item.epistemic is EpistemicStatus.UNRESOLVED for item in envelopes)


def test_web_search_timeout_is_unresolved(monkeypatch):
    monkeypatch.setattr(
        "ally.web.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("boom")),
    )
    from ally.fixtures import happy_path_input

    envelopes = DuckDuckGoSearcher().search(happy_path_input())
    assert envelopes[0].epistemic is EpistemicStatus.UNRESOLVED
    assert "timeout" in envelopes[0].text


def test_web_search_malformed_payload_is_unresolved(monkeypatch):
    def fake_get(*args, **kwargs):
        request = httpx.Request("GET", "https://api.duckduckgo.com/")
        return httpx.Response(200, text="not-json", request=request)

    monkeypatch.setattr("ally.web.httpx.get", fake_get)
    from ally.fixtures import happy_path_input

    envelopes = DuckDuckGoSearcher().search(happy_path_input())
    assert envelopes[0].epistemic is EpistemicStatus.UNRESOLVED
    assert "malformed" in envelopes[0].text


def test_http_fetch_timeout_is_unresolved(monkeypatch):
    monkeypatch.setattr(
        "ally.web.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("boom")),
    )
    envelope = HttpFetcher().fetch("https://example.com/press")
    assert envelope.epistemic is EpistemicStatus.UNRESOLVED
    assert "timeout" in envelope.text


def test_openfda_array_payload_is_unresolved(monkeypatch):
    def fake_get(*args, **kwargs):
        request = httpx.Request("GET", "https://api.fda.gov/drug/label.json")
        return httpx.Response(200, json=[1, 2], request=request)

    monkeypatch.setattr("ally.clinical.httpx.get", fake_get)
    envelopes = OpenFdaLabel().fetch(
        RetrievalQuery(brand_id="exampletide", task="approval")
    )
    assert envelopes[0].epistemic is EpistemicStatus.UNRESOLVED
