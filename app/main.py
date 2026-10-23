"""FastAPI app.  Run:  uvicorn app.main:app --reload"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .extractor import ExtractionError, extract
from .schemas import ExtractRequest, ExtractResponse

app = FastAPI(title="Data Extraction Bot", version="1.0.0")
STATIC = Path(__file__).parent / "static"


@app.exception_handler(ExtractionError)
async def extraction_error_handler(_, exc: ExtractionError):
    return JSONResponse(status_code=exc.status, content={"error": str(exc)})


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "model": config.GROQ_MODEL, "key_set": bool(config.GROQ_API_KEY)}


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(req: ExtractRequest):
    data, warnings = extract(req.text, req.doc_type)
    return ExtractResponse(
        doc_type=req.doc_type, model=config.GROQ_MODEL, data=data, warnings=warnings
    )
