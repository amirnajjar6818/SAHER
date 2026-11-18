# Local privacy models

These model files ship with the backend; runtime inference uses CPU and does not send images to a service.

| File | Upstream source | SHA-256 |
| --- | --- | --- |
| faces.onnx | [OpenCV YuNet 2023mar](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| plates.onnx | [open-image-models YOLOv9 tiny 640 license plates, assets release](https://github.com/ankandrew/open-image-models/releases/tag/assets) | `c3c1026ca7d0585dd88084d68182dd897113712fa734ae1557ca70174440c076` |

Upstream MIT notices are retained in FACE_LICENSE and PLATE_LICENSE. Models can miss small, occluded, rotated, unfamiliar or low quality faces/plates, including unfamiliar plate styles. Detection is not a guarantee of anonymization. Users must inspect the derived image, add missing rectangles, and confirm it before advancing an image beyond preparation. Only single-frame JPEG/PNG/WebP/BMP/TIFF images up to 24 megapixels are supported; PDF/video/animated image redaction is outside this image operation.
