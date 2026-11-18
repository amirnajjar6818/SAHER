import hashlib
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from services import workflow, workflow_antivirus as antivirus, workflow_images as images

BASE = "/api/v1/workflow"


def test_workflow_routes_are_unique():
    routes = [(route.path, method) for route in workflow.app.routes if getattr(route, "path", "").startswith(BASE) for method in route.methods]
    assert len(routes) == len(set(routes))


def clean(path):
    return {"status": "clean", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "engine": "test"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "DATA", tmp_path)
    monkeypatch.setattr(antivirus, "scan_file", clean)
    with TestClient(workflow.app) as c:
        credentials = {"username": "admin", "password": "admin-test-password"}
        assert c.post(BASE+"/auth/setup", json=credentials).status_code == 201
        c.post(BASE+"/auth/login", json=credentials)
        for name in ("alice", "bob"):
            c.post(BASE+"/auth/users", json={"username": name, "password": "member-test-password", "role": "reviewer"})
        yield c


def login(client, name):
    password = "admin-test-password" if name == "admin" else "member-test-password"
    assert client.post(BASE+"/auth/login", json={"username": name, "password": password}).status_code == 200


def upload(client, data=b"hello", name="note.txt", case_id=None):
    response = client.post(BASE, files={"file": (name, data)}, data={"source":"test", "permission":"owner", **({"case_id":case_id} if case_id else {})})
    assert response.status_code == 201, response.text
    return response.json()


def test_case_acl_every_file_route_and_revocation(client):
    case = client.post(BASE+"/cases", json={"kind":"case", "name":"private"}).json()
    private = upload(client)
    item = upload(client, case_id=case["id"])
    url = BASE+"/"+item["id"]
    login(client,"alice")
    assert client.get(BASE).json() == []
    assert client.get(BASE+"/cases").json() == []
    for path in ("original","export","redacted"):
        assert client.get(url+"/"+path).status_code == 404
    for path in ("inspect","extract","scan","redact","redact/confirm"):
        assert client.post(url+"/"+path,json={"version":item["version"]}).status_code == 404
    assert client.put(url,json=item).status_code == 404
    assert client.put(BASE+f'/cases/{case["id"]}/members/alice',json={"permission":"editor"}).status_code == 403
    login(client,"admin")
    client.put(BASE+f'/cases/{case["id"]}/members/alice',json={"permission":"viewer"})
    login(client,"alice")
    assert [r["id"] for r in client.get(BASE).json()] == [item["id"]]
    assert client.get(url+"/original").status_code == 200
    assert client.put(url,json=item).status_code == 404
    assert client.post(url+"/scan",json={"version":1}).status_code == 404
    login(client,"admin")
    client.put(BASE+f'/cases/{case["id"]}/members/alice',json={"permission":"editor"})
    login(client,"alice")
    assert client.put(url,json={**item,"case_id":None}).status_code == 403
    assert client.put(url,json={**item,"stage":1}).status_code == 200
    login(client,"admin")
    client.delete(BASE+f'/cases/{case["id"]}/members/alice')
    login(client,"alice")
    assert client.get(url+"/original").status_code == 404
    own = upload(client)
    assert client.get(BASE+"/"+own["id"]+"/original").status_code == 200
    login(client,"bob")
    assert client.get(BASE).json() == []
    assert client.get(BASE+"/"+private["id"]+"/original").status_code == 404
    assert client.get(BASE+"/"+own["id"]+"/original").status_code == 404


@pytest.mark.parametrize("state", ["infected", "unavailable"])
def test_quarantine_blocks_all_processing_until_rescan(client, monkeypatch, state):
    monkeypatch.setattr(antivirus,"scan_file",lambda p:{"status":state,"sha256":""})
    item=upload(client)
    url=BASE+"/"+item["id"]
    assert "file_check" not in item
    for path in ("original","export","redacted"):
        assert client.get(url+"/"+path).status_code == 423
    for path in ("extract","inspect","redact"):
        assert client.post(url+"/"+path,json={"version":1}).status_code == 423
    assert client.put(url,json={**item,"stage":1}).status_code == 423
    monkeypatch.setattr(antivirus,"scan_file",clean)
    item=client.post(url+"/scan",json={"version":1}).json()
    assert item["antivirus"]["status"] == "clean"
    assert client.get(url+"/original").status_code == 200
    (workflow.DATA/"originals"/item["id"]).write_bytes(b"changed")
    assert client.get(url+"/original").status_code == 423
    item=client.post(url+"/scan",json={"version":item["version"]}).json()
    assert item["antivirus"]["status"] == "changed"


def test_irreversible_mask_review_and_versioning(client,monkeypatch):
    raw=BytesIO()
    Image.new("RGB",(100,100),"white").save(raw,"PNG")
    monkeypatch.setattr(images,"detect",lambda image:[{"kind":"face","box":[20,20,40,40],"confidence":.9},{"kind":"plate","box":[60,60,80,80],"confidence":.9}])
    item=upload(client,raw.getvalue(),"image.png")
    url=BASE+"/"+item["id"]
    item=client.put(url,json={**item,"stage":1}).json()
    assert client.put(url,json={**item,"stage":2,"privacy_note":"checked"}).status_code == 422
    old=item["version"]
    item=client.post(url+"/redact",json={"version":old,"boxes":[[1,1,5,5]]}).json()
    assert len(item["redaction"]["boxes"]) == 3
    assert client.post(url+"/redact",json={"version":old}).status_code == 409
    masked=client.get(url+"/redacted")
    image=Image.open(BytesIO(masked.content))
    assert image.getpixel((30,30)) == (0,0,0)
    assert image.getpixel((70,70)) == (0,0,0)
    assert image.getpixel((2,2)) == (0,0,0)
    assert image.getpixel((95,95)) == (255,255,255)
    assert not image.info
    assert client.get(url+"/original").content == raw.getvalue()
    item=client.post(url+"/redact/confirm",json={"version":item["version"]}).json()
    assert item["redaction"]["confirmed"]
    assert client.put(url,json={**item,"stage":2,"privacy_note":"checked"}).status_code == 200


def test_detector_failure_does_not_create_output(client,monkeypatch):
    data=BytesIO();Image.new("RGB",(64,64),"white").save(data,"PNG")
    item=upload(client,data.getvalue(),"image.png")
    def fail(image): raise RuntimeError("missing model")
    monkeypatch.setattr(images,"detect",fail)
    url=BASE+"/"+item["id"]
    assert client.post(url+"/redact",json={"version":1}).status_code == 503
    assert client.get(url+"/redacted").status_code == 404
    assert not list((workflow.DATA/"redacted").iterdir())


def test_scanner_connection_failure_is_quarantined(tmp_path,monkeypatch):
    source=tmp_path/"file";source.write_bytes(b"sample")
    def fail(*args,**kwargs): raise OSError("scanner down")
    monkeypatch.setattr(antivirus.socket,"create_connection",fail)
    assert antivirus.scan_file(source)["status"] == "unavailable"


def test_legacy_unowned_records_and_cases_are_admin_only(client):
    item=upload(client)
    item.pop("owner")
    item["history"]=[]
    import json
    with workflow.connect() as db:
        db.execute("UPDATE records SET body=? WHERE id=?",(json.dumps(item),item["id"]))
        db.execute("INSERT INTO cases VALUES ('legacy', 'case', 'legacy')")
    login(client,"alice")
    assert client.get(BASE).json() == []
    assert client.get(BASE+"/cases").json() == []
    assert client.get(BASE+"/"+item["id"]+"/original").status_code == 404


@pytest.mark.parametrize("reply,status",[(b"stream: OK\0","clean"),(b"stream: Win.Test FOUND\0","infected"),(b"INSTREAM size limit exceeded. ERROR\0","unavailable")])
def test_clam_stream_protocol(tmp_path,monkeypatch,reply,status):
    connection=MagicMock()
    connection.__enter__.return_value=connection
    connection.recv.side_effect=[reply,b"ClamAV test/123\0"]
    monkeypatch.setattr(antivirus.socket,"create_connection",lambda *a,**k:connection)
    path=tmp_path/"file";path.write_bytes(b"abc")
    result=antivirus.scan_file(path)
    assert result["status"] == status
    sent=[call.args[0] for call in connection.sendall.call_args_list]
    assert sent[:3] == [b"zINSTREAM\0",b"\x00\x00\x00\x03abc",b"\x00\x00\x00\x00"]
    assert result["sha256"] == hashlib.sha256(b"abc").hexdigest()
