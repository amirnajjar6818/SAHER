"""Run inside the backend image on the compose network; uses isolated temporary files.

python scripts/verify_security_runtime.py /workspace/data/test-face.jpg /workspace/data/test-plate.jpg
"""
import hashlib
import sys
import tempfile
from pathlib import Path

from PIL import Image
from services.workflow_antivirus import scan_file
from services.workflow_images import mask


with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    sample = root / "input"
    sample.write_bytes(b"SAHER clean scanner integration test")
    result = scan_file(sample)
    assert result["status"] == "clean", result
    # Standard harmless antivirus test string, assembled and stored only in this container.
    sample.write_bytes(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}" + b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*")
    result = scan_file(sample)
    assert result["status"] == "infected", result
    print("ClamAV: clean and EICAR detection passed", result["engine"], result["signature"])
    for filename, expected in zip(sys.argv[1:], ("face", "plate")):
        source = Path(filename)
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        output = root / (expected+".png")
        result = mask(source, output, [])
        assert any(b["kind"] == expected for b in result["boxes"]), result
        image = Image.open(output)
        for box in result["boxes"]:
            x1,y1,x2,y2 = box["box"]
            assert image.getpixel(((x1+x2)//2,(y1+y2)//2)) == (0,0,0)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original
        assert not image.info
        print(expected+": real model detection, solid masks, stripped metadata and unchanged original passed; regions:", len(result["boxes"]))
