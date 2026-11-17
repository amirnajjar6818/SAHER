from fastapi.testclient import TestClient
from services import workflow


def test_workflow_starts_empty_and_requires_review(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DATA", tmp_path)
    with TestClient(workflow.app) as client:
        assert client.get("/api/v1/workflow").json() == []
        response = client.post("/api/v1/workflow", files={"file": ("note.txt", b"new content")},
                               data={"source": "manual", "permission": "owner"})
        assert response.status_code == 201
        item = response.json()
        url = "/api/v1/workflow/" + item["id"]
        assert client.get(url + "/export").status_code == 422
        assert client.put(url, json={**item, "stage": 3}).status_code == 422
        response = client.put(url, json={**item, "stage": 1})
        assert response.status_code == 200
        assert client.put(url, json=item).status_code == 409
        item = response.json()
        assert client.post(url + "/extract").json()["text"] == "new content"
        assert client.put(url, json={**item, "stage": 2}).status_code == 422
        item = client.put(url, json={**item, "stage": 2, "privacy_note": "checked"}).json()
        item = client.put(url, json={**item, "stage": 3, "category": "other", "evidence": "source"}).json()
        assert client.put(url, json={**item, "decision": "approved"}).status_code == 422
        item = client.put(url, json={**item, "decision": "approved", "reviewer": "reviewer", "template": "general"}).json()
        report = client.get(url + "/export")
        assert report.status_code == 200
        assert len(report.json()["history"]) == 5
    with TestClient(workflow.app) as client:
        assert len(client.get("/api/v1/workflow").json()) == 1
