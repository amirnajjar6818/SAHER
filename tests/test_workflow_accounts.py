from io import BytesIO
import hashlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from services import workflow, workflow_accounts

BASE = "/api/v1/workflow"


def test_visible_account_candidates_do_not_treat_email_as_handle():
    result = workflow_accounts.candidates("https://instagram.com/Example_1 @Example_1 @other contact@example.com https://t.me/example_1 https://instagram.com/p/123 evilinstagram.com/ignored")
    assert [(r["platform"], r["handle"].lower()) for r in result] == [("instagram","example_1"),("telegram","example_1"),("unknown","other")]


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(workflow,"DATA",tmp_path)
    monkeypatch.setattr(workflow.antivirus,"scan_file",lambda p:{"status":"clean","sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
    with TestClient(workflow.app) as client:
        credentials={"username":"admin","password":"admin-test-password"}
        client.post(BASE+"/auth/setup",json=credentials);client.post(BASE+"/auth/login",json=credentials)
        for user in ("alice","bob"):
            client.post(BASE+"/auth/users",json={"username":user,"password":"member-test-password","role":"editor"})
        yield client


def login(client,user):
    assert client.post(BASE+"/auth/login",json={"username":user,"password":"admin-test-password" if user=="admin" else "member-test-password"}).status_code == 200


def upload(client):
    data=BytesIO();Image.new("RGB",(100,100),"white").save(data,"PNG")
    response=client.post(BASE,files={"file":("photo.png",data.getvalue())},data={"source":"test","permission":"owner"})
    assert response.status_code==201,response.text
    return response.json()


def organize(client,item,platform="instagram",handle="example",category=""):
    return client.post(BASE+"/"+item["id"]+"/organize",json={"version":item["version"],"platform":platform,"handle":handle,"category":category})


def test_ocr_suggestions_require_confirmation(client,monkeypatch):
    login(client,"alice");item=upload(client)
    monkeypatch.setattr(workflow,"extract",lambda *args:{"text":"instagram.com/Example_1 @other","version":1})
    url=BASE+"/"+item["id"]
    result=client.post(url+"/analyze-image",json={"version":1})
    assert result.status_code==200,result.text
    item=result.json()
    assert item["account_candidates"][0]["handle"]=="Example_1"
    assert not item.get("account_id")
    assert client.get(BASE+"/accounts").json()=={"folders":[],"pending":1}
    assert client.post(url+"/analyze-image",json={"version":1}).status_code==409
    assert organize(client,item,category="invented").status_code==422
    assert organize(client,item,platform="unknown").status_code==422
    assert organize(client,item,handle="../path").status_code==422
    saved=organize(client,item,handle="Example_1",category="اجتماعی").json()
    assert saved["account"]["handle"]=="example_1"
    assert saved["account"]["confirmed_by"]=="alice"
    assert organize(client,item).status_code==409
    folder=client.get(BASE+"/accounts").json()["folders"][0]
    assert folder["categories"]=={"اجتماعی":1}
    assert folder["total"]==1


def test_folder_keys_separate_network_owner_and_case(client):
    login(client,"alice")
    first=organize(client,upload(client),handle="Same").json()
    second=organize(client,upload(client),handle="same").json()
    other_network=organize(client,upload(client),platform="telegram",handle="same").json()
    assert first["account_id"]==second["account_id"]
    assert first["account_id"]!=other_network["account_id"]
    login(client,"bob")
    private=organize(client,upload(client),handle="same").json()
    assert private["account_id"]!=first["account_id"]
    assert len(client.get(BASE+"/accounts").json()["folders"])==1
    assert organize(client,first).status_code==404
    assert client.get(BASE+"/"+first["id"]+"/preview").status_code==404
    assert client.post(BASE+"/"+first["id"]+"/analyze-image",json={"version":first["version"]}).status_code==404
    login(client,"alice")
    case=client.post(BASE+"/cases",json={"kind":"case","name":"scoped"}).json()
    moved=client.put(BASE+"/"+first["id"],json={**first,"case_id":case["id"]}).json()
    assert moved["account_id"] is None
    assert moved["account"] is None
    moved=organize(client,moved).json()
    assert moved["account_id"]!=first["account_id"]
    login(client,"bob")
    assert [r["id"] for r in client.get(BASE+"/accounts").json()["folders"]]==[private["account_id"]]


def test_account_operations_are_blocked_for_quarantined_image(client,monkeypatch):
    item=upload(client)
    monkeypatch.setattr(workflow.antivirus,"scan_file",lambda p:{"status":"infected","sha256":""})
    item=client.post(BASE+"/"+item["id"]+"/scan",json={"version":1}).json()
    assert organize(client,item).status_code==423
    assert client.get(BASE+"/"+item["id"]+"/preview").status_code==423
    assert client.post(BASE+"/"+item["id"]+"/analyze-image",json={"version":item["version"]}).status_code==423
