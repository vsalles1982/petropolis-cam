import re
import time
import urllib.parse
import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/climaaovivo", tags=["ClimaAoVivo"])

DOMAIN = "climaaovivo.com.br"
SITE_BASE = "https://" + DOMAIN
API_BASE = "https://cmsv2." + DOMAIN + "/api/cameras"

STREAM_CACHE = {}
CAM_SLUGS = {}
CACHE_TTL = 180

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": SITE_BASE + "/",
    "Origin": SITE_BASE
}

async def get_fresh_stream_info(descodigo: str) -> dict:
    now = time.time()
    cached = STREAM_CACHE.get(descodigo)
    if cached and cached["expires"] > now:
        return cached

    async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=15.0, follow_redirects=True) as client:
        if descodigo not in CAM_SLUGS:
            list_resp = await client.get(API_BASE)
            list_resp.raise_for_status()
            for c in list_resp.json().get("data", []):
                code = c.get("descodigo")
                if code:
                    CAM_SLUGS[code] = c["desurl"]

        if descodigo not in CAM_SLUGS:
            raise HTTPException(status_code=404, detail="Câmera não encontrada no mapa da API")

        slug = CAM_SLUGS[descodigo]
        cam_resp = await client.get(f"{API_BASE}/{slug}")
        cam_resp.raise_for_status()
        cam_data = cam_resp.json().get("data", {})

        m3u8_url = cam_data.get("link")
        if not m3u8_url or "playlist.m3u8" not in m3u8_url:
            raise HTTPException(status_code=502, detail="Link HLS não retornado pela API individual")

        token_match = re.search(r'wmsAuthSign=([^&]+)', m3u8_url)
        token = token_match.group(1) if token_match else ""

        info = {
            "m3u8_url": m3u8_url,
            "token": token,
            "expires": now + CACHE_TTL
        }
        STREAM_CACHE[descodigo] = info
        return info

@router.get("/stream/{descodigo}")
@router.get("/stream")
async def proxy_playlist(request: Request, descodigo: str = None):
    cam_code = descodigo or request.query_params.get("codigo") or request.query_params.get("code") or request.query_params.get("id")
    if not cam_code:
        raise HTTPException(status_code=400, detail="Código da câmera ausente")

    info = await get_fresh_stream_info(cam_code)
    m3u8_url = info["m3u8_url"]
    token = info["token"]

    async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(m3u8_url)
        if resp.status_code != 200:
            STREAM_CACHE.pop(cam_code, None)
            raise HTTPException(status_code=resp.status_code, detail=f"Erro {resp.status_code} ao obter playlist")

        base_stream_url = urllib.parse.urljoin(m3u8_url, ".")
        rewritten_lines = []

        for line in resp.text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                rewritten_lines.append(line)
            else:
                target_url = urllib.parse.urljoin(base_stream_url, s)
                if token and "wmsAuthSign=" not in target_url:
                    sep = "&" if "?" in target_url else "?"
                    target_url = f"{target_url}{sep}wmsAuthSign={token}"
                
                encoded_url = urllib.parse.quote(target_url, safe="")
                if ".m3u8" in s:
                    rewritten_lines.append(f"/api/climaaovivo/subplaylist?url={encoded_url}")
                else:
                    rewritten_lines.append(f"/api/climaaovivo/segment?url={encoded_url}")

        return Response(
            content="\n".join(rewritten_lines),
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

@router.get("/subplaylist")
async def proxy_subplaylist(url: str):
    decoded_url = urllib.parse.unquote(url)
    base_url = urllib.parse.urljoin(decoded_url, ".")
    
    token_match = re.search(r'wmsAuthSign=([^&]+)', decoded_url)
    token = token_match.group(1) if token_match else ""

    async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(decoded_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Erro ao obter subplaylist")

        rewritten_lines = []
        for line in resp.text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                rewritten_lines.append(line)
            else:
                target_url = urllib.parse.urljoin(base_url, s)
                if token and "wmsAuthSign=" not in target_url:
                    sep = "&" if "?" in target_url else "?"
                    target_url = f"{target_url}{sep}wmsAuthSign={token}"
                
                encoded_url = urllib.parse.quote(target_url, safe="")
                rewritten_lines.append(f"/api/climaaovivo/segment?url={encoded_url}")

        return Response(
            content="\n".join(rewritten_lines),
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

@router.get("/segment")
async def proxy_segment(url: str):
    decoded_url = urllib.parse.unquote(url)

    async def iterfile():
        async with httpx.AsyncClient(headers=BASE_HEADERS, timeout=20.0, follow_redirects=True) as client:
            async with client.stream("GET", decoded_url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Erro no segmento")
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="video/mp2t",
        headers={"Access-Control-Allow-Origin": "*"}
    )
