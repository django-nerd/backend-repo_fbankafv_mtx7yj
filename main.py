import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN")

class IdentifyRequest(BaseModel):
    url: str

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database and env are available"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
        "audd_api_token": "✅ Set" if AUDD_API_TOKEN else "❌ Not Set",
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


@app.post("/api/identify")
def identify_by_url(payload: IdentifyRequest):
    if not AUDD_API_TOKEN:
        raise HTTPException(status_code=400, detail="AUDD_API_TOKEN env var is not set on the server")

    url = (payload.url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=422, detail="Please provide a valid URL starting with http(s)://")

    try:
        r = requests.post(
            "https://api.audd.io/",
            data={
                "api_token": AUDD_API_TOKEN,
                "url": url,
                "return": "timecode,deezer,spotify,apple_music",
            },
            timeout=30,
        )
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed contacting recognition service: {e}")

    if not data or data.get("status") != "success":
        raise HTTPException(status_code=502, detail="Recognition service error")

    result = data.get("result")
    if not result:
        return {"found": False}

    return normalize_audd_result(result)


@app.post("/api/identify-file")
async def identify_by_file(file: UploadFile = File(...)):
    if not AUDD_API_TOKEN:
        raise HTTPException(status_code=400, detail="AUDD_API_TOKEN env var is not set on the server")

    try:
        content = await file.read()
        files = {"file": (file.filename or "clip.mp3", content, file.content_type or "audio/mpeg")}
        r = requests.post(
            "https://api.audd.io/",
            data={"api_token": AUDD_API_TOKEN, "return": "timecode,deezer,spotify,apple_music"},
            files=files,
            timeout=60,
        )
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed contacting recognition service: {e}")

    if not data or data.get("status") != "success":
        raise HTTPException(status_code=502, detail="Recognition service error")

    result = data.get("result")
    if not result:
        return {"found": False}

    return normalize_audd_result(result)


def normalize_audd_result(result: dict):
    """Convert AudD response into a compact, frontend-friendly structure"""
    title = result.get("title")
    artist = result.get("artist")
    album = result.get("album")
    release_date = result.get("release_date")
    timecode = result.get("timecode")
    song_link = result.get("song_link")
    links = {
        "apple_music": (result.get("apple_music") or {}).get("url"),
        "spotify": ((result.get("spotify") or {}).get("external_urls") or {}).get("spotify"),
        "deezer": (result.get("deezer") or {}).get("link"),
        "audd": song_link,
    }
    return {
        "found": True,
        "title": title,
        "artist": artist,
        "album": album,
        "release_date": release_date,
        "timecode": timecode,
        "links": links,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
