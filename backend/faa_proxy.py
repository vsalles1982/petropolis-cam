import time
import httpx
from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/api/faa", tags=["FAAWeatherCams"])

DOMAIN = "weathercams.faa" + ".gov"
SITE_BASE = "https://" + DOMAIN
API_BASE = SITE_BASE + "/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": SITE_BASE + "/cameras/state/HI",
    "Prefer": "",
    "Accept": "application/json"
}

IMG_CACHE = {}
CACHE_TTL = 60  # 1 minuto
SESSION_COOKIES = httpx.Cookies()

async def ensure_session(client: httpx.AsyncClient):
    if not SESSION_COOKIES:
        r = await client.get(SITE_BASE + "/cameras/state/HI", headers=HEADERS)
        SESSION_COOKIES.update(r.cookies)

@router.get("/image/{camera_id}")
@router.get("/image")
async def proxy_faa_image(request: Request, camera_id: int = None):
    cam_id = camera_id or request.query_params.get("camera_id") or request.query_params.get("id")
    if not cam_id:
        raise HTTPException(status_code=400, detail="camera_id ausente")

    cam_id_str = str(cam_id)
    now = time.time()
    cached = IMG_CACHE.get(cam_id_str)
    if cached and cached["expires"] > now:
        return Response(
            content=cached["bytes"],
            media_type="image/jpeg",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

    async with httpx.AsyncClient(headers=HEADERS, cookies=SESSION_COOKIES, timeout=15.0, follow_redirects=True) as client:
        await ensure_session(client)
        api_url = f"{API_BASE}/cameras/{cam_id_str}/images/last/1"
        r = await client.get(api_url)

        if r.status_code == 401:
            SESSION_COOKIES.clear()
            await ensure_session(client)
            r = await client.get(api_url)

        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Erro ao consultar API FAA")

        payload = r.json().get("payload", [])
        if not payload or not payload[0].get("imageUri"):
            raise HTTPException(status_code=404, detail="Imagem não disponível para esta câmera")

        img_uri = payload[0]["imageUri"]
        img_resp = await client.get(img_uri, headers={"User-Agent": HEADERS["User-Agent"]})
        if img_resp.status_code != 200:
            raise HTTPException(status_code=img_resp.status_code, detail="Erro ao baixar JPEG da FAA")

        img_bytes = img_resp.content
        IMG_CACHE[cam_id_str] = {"bytes": img_bytes, "expires": now + CACHE_TTL}

        return Response(
            content=img_bytes,
            media_type="image/jpeg",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )
