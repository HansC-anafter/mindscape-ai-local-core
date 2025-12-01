# OCR Service

Local PaddleOCR service for text extraction from images and PDFs.

## Overview

This service provides OCR (Optical Character Recognition) capabilities using PaddleOCR, specifically designed for processing government grant documents and scanned PDFs.

## Hardware Requirements

### Recommended Configuration (Comfortable Usage)

- **CPU**: 8 physical cores (Desktop i7 / Ryzen 7 level)
- **RAM**: 32GB
- **GPU**: NVIDIA RTX 3060 / 4060 level, VRAM ≥ 8GB (Linux/Windows only, strongly recommended)
- **SSD**: ≥ 512GB (system + models + file storage)

### CPU-only Alternative (Slower)

- **CPU**: 12-16 cores
- **RAM**: 32GB
- **GPU**: None (CPU-only processing)

### macOS Support

**Important**: macOS (Intel or Apple Silicon) only supports CPU mode. PaddlePaddle does not support Metal/GPU acceleration on macOS. The service will automatically use CPU mode on macOS.

**Note**: Below these specifications, local OCR is not recommended. Use cloud OCR service instead.

## API Endpoints

### Health Check

```
GET /health
```

Returns service status and GPU availability.

### Image OCR

```
POST /ocr/image
```

Process single image file. Accepts multipart/form-data with image file.

**Response**:
```json
{
  "text": "Full extracted text",
  "blocks": [
    {
      "text": "Line text",
      "confidence": 0.98,
      "bbox": [x1, y1, x2, y2]
    }
  ],
  "page": 1
}
```

### PDF OCR

```
POST /ocr/pdf
```

Process PDF file (multi-page). Accepts multipart/form-data with PDF file.

**Response**:
```json
{
  "pages": [
    {
      "page": 1,
      "text": "...",
      "blocks": [...]
    }
  ],
  "total_pages": 2
}
```

### Local File Path Endpoints

For integration with local file system tools:

- `POST /ocr/image/path` - Process image from local file path
- `POST /ocr/pdf/path` - Process PDF from local file path

## Configuration

Environment variables:

- `OCR_USE_GPU`: Enable GPU acceleration (default: auto-detect, or set `true`/`false` to force)
- `OCR_LANG`: Language code (default: `ch` for Chinese-English mixed)
  - Common codes: `ch` (Chinese-English), `en` (English only), `chinese_cht` (Traditional Chinese)
  - See PaddleOCR documentation for full language list

## Development

### Local Development

```bash
cd ocr-service
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### Docker

```bash
docker compose build ocr-service
docker compose up ocr-service
```

## Integration

This service is integrated into Mindscape AI's Core File Tools capability pack. The service automatically handles:

- Scanned PDF detection
- Image text extraction
- Quality confidence scoring

## License

MIT License - See main project LICENSE file.




