"""Offline face/plate detection and irreversible, metadata-free image derivatives."""
import hashlib
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

_lock = threading.Lock()
_engines = None


def engines():
    global _engines
    if _engines is None:
        import cv2
        import onnxruntime as ort
        root = Path(os.environ.get("SAHER_PRIVACY_MODELS", str(Path(__file__).resolve().parents[1] / "vendor/privacy-models")))
        for name, digest in {"faces.onnx": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", "plates.onnx": "c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076"}.items():
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Privacy model checksum mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        face = cv2.FaceDetectorYN.create(str(root / "faces.onnx"), "", (320, 320), 0.6, 0.3, 5000)
        plates = ort.InferenceSession(str(root / "plates.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
        _engines = face, plates
    return _engines


def detect(image):
    import cv2
    import numpy as np
    with _lock:
        face, plates = engines()
        # Bound CPU and working memory; coordinates are mapped back to full resolution.
        scale = min(1.0, 1600 / max(image.size))
        small = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))
        pixels = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2BGR)
        face.setInputSize(small.size)
        _, found = face.detect(pixels)
        boxes = []
        if found is not None:
            for row in found:
                x, y, w, h = [float(v) / scale for v in row[:4]]
                boxes.append({"kind": "face", "box": [x, y, x+w, y+h], "confidence": float(row[-1])})
        # YOLOv9 end-to-end ONNX uses letterbox RGB NCHW input and Nx7 output.
        ratio = min(640 / small.width, 640 / small.height)
        width, height = round(small.width * ratio), round(small.height * ratio)
        dw, dh = (640-width)/2, (640-height)/2
        resized = cv2.resize(pixels, (width, height))
        padded = cv2.copyMakeBorder(resized, round(dh-.1), round(dh+.1), round(dw-.1), round(dw+.1), cv2.BORDER_CONSTANT, value=(114,114,114))
        tensor = np.ascontiguousarray(padded[:, :, ::-1].transpose(2,0,1)[None], dtype=np.float32) / 255
        predictions = plates.run(None, {plates.get_inputs()[0].name: tensor})[0]
        predictions = predictions.reshape(-1, 7)
        for row in predictions:
            if float(row[6]) >= .25:
                x1,y1,x2,y2 = row[1:5]
                boxes.append({"kind": "plate", "box": [float((x1-dw)/ratio/scale), float((y1-dh)/ratio/scale), float((x2-dw)/ratio/scale), float((y2-dh)/ratio/scale)], "confidence": float(row[6])})
        return boxes


def mask(source, target, manual, previous=None):
    try:
        with Image.open(source) as original:
            if original.format not in {"JPEG", "PNG", "WEBP", "BMP", "TIFF"} or getattr(original, "n_frames", 1) != 1:
                raise HTTPException(415, "پوشاندن خودکار برای تصویر ثابت JPEG، PNG، WebP، BMP و TIFF است")
            if original.width * original.height > 24_000_000:
                raise HTTPException(413, "برای پوشاندن، تصویر باید حداکثر ۲۴ میلیون پیکسل باشد")
            normalized = ImageOps.exif_transpose(original).convert("RGBA")
            image = Image.new("RGBA", normalized.size, "white")
            image.alpha_composite(normalized)
            image = image.convert("RGB")
        try:
            boxes = detect(image)
        except Exception as error:
            raise HTTPException(503, "مدل تشخیص در دسترس نیست؛ نسخهٔ پوشانده‌شده ساخته نشد") from error
        # Preserve every previous mask, including manually added regions.
        if previous:
            boxes.extend(previous.get("boxes", []))
        for coords in manual:
            if len(coords) != 4 or any(not math.isfinite(v) for v in coords):
                raise HTTPException(422, "مختصات پوشاندن معتبر نیست")
            x1,y1,x2,y2 = coords
            if not (0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height):
                raise HTTPException(422, "ناحیه باید داخل تصویر باشد")
            boxes.append({"kind": "manual", "box": coords, "confidence": 1})
        draw = ImageDraw.Draw(image)
        regions = []
        seen = set()
        for box in boxes:
            x1,y1,x2,y2 = box["box"]
            if x2 <= x1 or y2 <= y1:
                continue
            padding = 0 if box.get("padded") or box["kind"] == "manual" else .15
            dx,dy = (x2-x1)*padding, (y2-y1)*padding
            coords = [max(0, math.floor(x1-dx)), max(0, math.floor(y1-dy)), min(image.width-1, math.ceil(x2+dx)), min(image.height-1, math.ceil(y2+dy))]
            if coords[2] < coords[0] or coords[3] < coords[1]:
                continue
            key = tuple(coords)
            if key in seen:
                continue
            seen.add(key)
            draw.rectangle(coords, fill="black")
            regions.append({**box, "box": coords, "padded": True})
        image.info.clear()
        image.save(target, "PNG")
        return {"filename": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "width": image.width, "height": image.height,
                "boxes": regions, "confirmed": False, "models": "YuNet-2023mar + YOLOv9-t-640-license-plates", "at": datetime.now(timezone.utc).isoformat()}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "تصویر معتبر و قابل پردازش نیست") from error
