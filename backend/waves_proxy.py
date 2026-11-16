import urllib.parse
import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/wavesnow", tags=["WavesNow"])

SITE_BASE = "https://wavesnow" + ".com.br"
CF_BASE = "https://d1pn38aa7xeaye." + "cloudfront.net/BrasilCameras/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": SITE_BASE + "/",
    "Origin": SITE_BASE
}

@router.get("/stream/{code}")
@router.get("/stream")
async def proxy_playlist(request: Request, code: str = None):
    cam_code = code or request.query_params.get("code") or request.query_params.get("codigo")
    if not cam_code:
        raise HTTPException(status_code=400, detail="Código da câmera WavesNow ausente")

    base_url = f"{CF_BASE}{cam_code}/"
    playlist_url = f"{base_url}playlist.m3u8"

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(playlist_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Erro {resp.status_code} ao obter playlist WavesNow")

        rewritten = []
        for line in resp.text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                rewritten.append(line)
            else:
                target_url = urllib.parse.urljoin(base_url, s)
                encoded_url = urllib.parse.quote(target_url, safe="")
                if ".m3u8" in s:
                    rewritten.append(f"/api/wavesnow/subplaylist?url={encoded_url}")
                else:
                    rewritten.append(f"/api/wavesnow/segment?url={encoded_url}")

        return Response(
            content="\n".join(rewritten),
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

@router.get("/subplaylist")
async def proxy_subplaylist(url: str):
    decoded_url = urllib.parse.unquote(url)
    base_url = urllib.parse.urljoin(decoded_url, ".")

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(decoded_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Erro ao obter subplaylist WavesNow")

        rewritten = []
        for line in resp.text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                rewritten.append(line)
            else:
                target_url = urllib.parse.urljoin(base_url, s)
                encoded_url = urllib.parse.quote(target_url, safe="")
                rewritten.append(f"/api/wavesnow/segment?url={encoded_url}")

        return Response(
            content="\n".join(rewritten),
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

@router.get("/segment")
async def proxy_segment(url: str):
    decoded_url = urllib.parse.unquote(url)

    async def iterfile():
        async with httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
            async with client.stream("GET", decoded_url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Erro no segmento WavesNow")
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="video/mp2t",
        headers={"Access-Control-Allow-Origin": "*"}
    )
