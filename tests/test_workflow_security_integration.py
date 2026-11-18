"""Opt-in integration: real ClamAV and local ONNX models, isolated archive."""
import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import workflow

pytestmark = pytest.mark.skipif(os.environ.get("SAHER_SECURITY_INTEGRATION") != "1", reason="requires running ClamAV and fixture images")
BASE="/api/v1/workflow"


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(workflow,"DATA",tmp_path)
    with TestClient(workflow.app) as c:
        credentials={"username":"integration-admin","password":"integration-test-password"}
        c.post(BASE+"/auth/setup",json=credentials)
        c.post(BASE+"/auth/login",json=credentials)
        yield c


def test_real_clamav_quarantines_eicar_upload(client):
    sample=b"X5O!P%@AP[4\\PZX54(P^)7CC)7}"+b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    response=client.post(BASE,files={"file":("test.txt",sample)},data={"source":"integration","permission":"test"})
    assert response.status_code == 201,response.text
    item=response.json()
    assert item["antivirus"]["status"] == "infected"
    assert "Eicar" in item["antivirus"]["signature"]
    assert client.get(BASE+"/"+item["id"]+"/original").status_code == 423
    assert client.post(BASE+"/"+item["id"]+"/extract").status_code == 423


@pytest.mark.parametrize("sample,kind",[("test-face.jpg","face"),("test-plate.jpg","plate")])
def test_real_models_image_workflow_and_word(client,sample,kind):
    original=(Path("data")/sample).read_bytes()
    response=client.post(BASE,files={"file":(sample,original)},data={"source":"integration","permission":"test"})
    assert response.status_code == 201,response.text
    item=response.json()
    assert item["antivirus"]["status"] == "clean"
    url=BASE+"/"+item["id"]
    item=client.put(url,json={**item,"stage":1}).json()
    response=client.post(url+"/redact",json={"version":item["version"]})
    assert response.status_code == 200,response.text
    item=response.json()
    assert any(b["kind"]==kind for b in item["redaction"]["boxes"])
    masked=client.get(url+"/redacted").content
    assert masked != original
    assert client.get(url+"/original").content == original
    item=client.post(url+"/redact/confirm",json={"version":item["version"]}).json()
    item=client.put(url,json={**item,"stage":2,"privacy_note":"image reviewed"}).json()
    item=client.put(url,json={**item,"stage":3,"category":"test","evidence":"fixture"}).json()
    response=client.put(url,json={**item,"decision":"reviewed","template":"test"})
    assert response.status_code == 200,response.text
    response=client.get(url+"/export?format=docx")
    assert response.status_code == 200,response.text
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        media=[archive.read(name) for name in archive.namelist() if name.startswith("word/media/")]
    assert media == [masked]


def test_real_ocr_multiple_images_group_after_confirmation(client):
    from PIL import Image, ImageDraw, ImageFont
    folders=[]
    for index,(url,platform) in enumerate((("instagram.com/bright_archive","instagram"),("instagram.com/bright_archive","instagram"),("t.me/bright_archive","telegram"))):
        image=Image.new("RGB",(1300,260),"white")
        ImageDraw.Draw(image).text((35,80),url,font=ImageFont.load_default(size=58),fill="black")
        data=BytesIO();image.save(data,"PNG")
        response=client.post(BASE,files={"file":(f"batch-{index}.png",data.getvalue())},data={"source":"batch integration","permission":"fixture"})
        assert response.status_code==201,response.text
        item=response.json()
        path=BASE+"/"+item["id"]
        response=client.post(path+"/analyze-image",json={"version":item["version"]})
        assert response.status_code==200,response.text
        item=response.json()
        assert not item.get("account_id")
        assert any(c["platform"]==platform and c["handle"].lower()=="bright_archive" for c in item["account_candidates"]),item["text"]
        response=client.post(path+"/organize",json={"version":item["version"],"platform":platform,"handle":"bright_archive","category":"اجتماعی"})
        assert response.status_code==200,response.text
        folders.append(response.json()["account_id"])
    assert folders[0]==folders[1]
    assert folders[2]!=folders[0]
    result=client.get(BASE+"/accounts").json()
    assert sorted(f["total"] for f in result["folders"])==[1,2]
    assert result["pending"]==0
