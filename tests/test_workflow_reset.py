from fastapi.testclient import TestClient
from services import workflow


def test_workflow_starts_empty_and_requires_review(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DATA", tmp_path)
    import hashlib
    monkeypatch.setattr(workflow.antivirus, "scan_file", lambda path: {"status": "clean", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    with TestClient(workflow.app) as client:
        credentials = {"username": "admin", "password": "test-password-123"}
        assert client.get("/api/v1/workflow").status_code == 401
        assert client.post("/api/v1/workflow/auth/setup", json=credentials).status_code == 201
        assert client.post("/api/v1/workflow/auth/login", json=credentials).status_code == 200
        privacy = client.post("/api/v1/workflow/privacy",
                              json={"text": "email test@example.com phone 09123456789 name Ali", "terms": ["Ali"]}).json()
        assert privacy["count"] == 3
        assert "test@example.com" not in privacy["text"]
        assert "09123456789" not in privacy["text"]
        assert client.get("/api/v1/workflow").json() == []
        response = client.post("/api/v1/workflow", files={"file": ("note.txt", b"new content")},
                               data={"source": "manual", "permission": "owner"})
        assert response.status_code == 201
        item = response.json()
        url = "/api/v1/workflow/" + item["id"]
        original = client.get(url + "/original")
        assert original.content == b"new content"
        assert original.headers["content-disposition"] == 'attachment; filename="note.txt"'
        assert client.get(url + "/export").status_code == 422
        assert client.put(url, json={**item, "stage": 3}).status_code == 422
        response = client.put(url, json={**item, "stage": 1})
        assert response.status_code == 200
        assert client.put(url, json=item).status_code == 409
        item = response.json()
        assert client.post(url + "/extract").json()["text"] == "new content"
        item["text"] = "new content"
        inspection = client.post(url + "/inspect").json()
        assert inspection["signature_valid"] is True
        assert inspection["integrity"] is True
        assert client.put(url, json={**item, "stage": 2}).status_code == 422
        item = client.put(url, json={**item, "stage": 2, "privacy_note": "checked"}).json()
        case_payload = {"kind": "event", "name": "Example"}
        case_response = client.post("/api/v1/workflow/cases", json=case_payload)
        assert case_response.status_code == 201
        case = case_response.json()
        assert client.post("/api/v1/workflow/cases", json=case_payload).status_code == 409
        assert client.put(url, json={**item, "case_id": "missing"}).status_code == 422
        item.update(case_id=case["id"], case_name="incorrect")
        item = client.put(url, json={**item, "stage": 3, "category": "other", "evidence": "source"}).json()
        assert item["case_name"] == case["name"]
        assert client.put(url, json={**item, "decision": "approved"}).status_code == 422
        item = client.put(url, json={**item, "decision": "approved", "reviewer": "reviewer", "template": "general"}).json()
        report = client.get(url + "/export")
        assert report.status_code == 200
        word = client.get(url + "/export?format=docx")
        assert word.status_code == 200
        from io import BytesIO
        from docx import Document
        assert "new content" in [p.text for p in Document(BytesIO(word.content)).paragraphs]
        assert len(report.json()["history"]) == 5
        assert report.json()["case_id"] == case["id"]
        returned = client.put(url, json={**item, "stage": 2}).json()
        assert returned["decision"] == ""
        revised = client.put(url, json={**returned, "stage": 3, "evidence": "new source",
                                       "decision": item["decision"]}).json()
        assert revised["decision"] == ""
        assert client.get(url + "/export").status_code == 422
        approved = client.put(url, json={**revised, "decision": "approved again"}).json()
        assert client.get(url + "/export").status_code == 200
        assert approved["reviewer"] == "admin"
        editor = {"username": "editor", "password": "editor-password-123"}
        assert client.post("/api/v1/workflow/auth/users", json={**editor, "role": "editor"}).status_code == 201
        assert client.put(f'/api/v1/workflow/cases/{case["id"]}/members/editor', json={"permission": "editor"}).status_code == 200
        preferences = {"categories": ["custom"], "templates": ["general"], "sources": ["manual"]}
        assert client.put("/api/v1/workflow/settings", json=preferences).status_code == 200
        assert client.post("/api/v1/workflow/auth/login", json=editor).status_code == 200
        assert client.put(url, json={**approved, "decision": "editor approval"}).status_code == 403
        assert client.put("/api/v1/workflow/settings", json=preferences).status_code == 403
        assert client.post("/api/v1/workflow/auth/logout").status_code == 200
        assert client.get(url + "/original").status_code == 401
        assert client.post("/api/v1/workflow/auth/login", json=credentials).status_code == 200
        changed = client.put(url, json={**approved, "unknowns": "new question"}).json()
        assert changed["decision"] == ""
        assert client.get(url + "/export").status_code == 422
    with TestClient(workflow.app) as client:
        assert client.post("/api/v1/workflow/auth/login", json=credentials).status_code == 200
        assert len(client.get("/api/v1/workflow").json()) == 1
        assert client.get("/api/v1/workflow/cases").json() == [case]


def test_online_settings_and_provider_responses(tmp_path, monkeypatch):
    from services import workflow_online
    monkeypatch.setattr(workflow, "DATA", tmp_path)
    credentials = {"username": "admin", "password": "test-password-123"}
    with TestClient(workflow.app) as client:
        client.post("/api/v1/workflow/auth/setup", json=credentials)
        client.post("/api/v1/workflow/auth/login", json=credentials)
        assert client.post("/api/v1/workflow/online/analyze", json={"text": "content"}).status_code == 422
        config = {"provider": "openai", "model": "test-model", "api_key": "private-key",
                  "search_key": "search-secret"}
        response = client.put("/api/v1/workflow/online", json=config)
        assert response.status_code == 200
        assert "private-key" not in response.text and "search-secret" not in response.text
        assert client.get("/api/v1/workflow/online").json()["configured"] is True

        def fake_request(url, headers, payload=None):
            if "brave" in url:
                assert headers["X-Subscription-Token"] == "search-secret"
                return {"web": {"results": [{"title": "source", "url": "https://example.com",
                                              "description": "excerpt"}]}}
            assert headers["Authorization"] == "Bearer private-key"
            assert payload["messages"][1]["content"] == "content"
            return {"choices": [{"message": {"content": "suggested summary"}}]}

        monkeypatch.setattr(workflow_online, "request_json", fake_request)
        assert client.post("/api/v1/workflow/online/analyze",
                           json={"text": "content"}).json()["text"] == "suggested summary"
        assert client.post("/api/v1/workflow/online/search",
                           json={"query": "source"}).json()["results"][0]["url"] == "https://example.com"
        changed = client.put("/api/v1/workflow/online",
                             json={"provider": "openrouter", "model": "another-model"}).json()
        assert changed["configured"] is False
        assert changed["search_configured"] is True
