"""
Proxy HLS isolado para câmeras PREMIUM do Surfline (origem = 'surfline_premium').

- Réplica do surfline_proxy.py (mesmos headers Referer/Origin exigidos pelo
  CloudFront do cdn-surfline.com), mas com prefixo /api/surfline_premium.
- Anti-SSRF: só libera hosts no cdn-surfline.com (hls.cdn-surfline.com).
- Blindagem: URLs no banco começam com /api/surfline_premium/... e o
  limpar_offline.py as ignora automaticamente (regra "/api/").
"""
import urllib.parse
import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/surfline_premium", tags=["Surfline Premium"])

SITE_BASE = "".join(["https://", "www.surfline", ".com"])
ALLOWED_HOST = "".join(["hls.cdn-surfline", ".com"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": SITE_BASE + "/",
    "Origin": SITE_BASE
}

def validate_surfline_url(decoded_url: str):
    parsed = urllib.parse.urlparse(decoded_url)
    if parsed.scheme != "https" or parsed.netloc != ALLOWED_HOST:
        raise HTTPException(status_code=400, detail="Host de stream inválido")

@router.get("/stream")
async def proxy_playlist(url: str):
    decoded_url = urllib.parse.unquote(url)
    validate_surfline_url(decoded_url)
    base_url = urllib.parse.urljoin(decoded_url, ".")

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(decoded_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Erro {resp.status_code} ao obter playlist Surfline Premium")

        rewritten = []
        for line in resp.text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                rewritten.append(line)
            else:
                target_url = urllib.parse.urljoin(base_url, s)
                encoded_url = urllib.parse.quote(target_url, safe="")
                if ".m3u8" in s:
                    rewritten.append(f"/api/surfline_premium/stream?url={encoded_url}")
                else:
                    rewritten.append(f"/api/surfline_premium/segment?url={encoded_url}")

        return Response(
            content="\n".join(rewritten),
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
        )

@router.get("/segment")
async def proxy_segment(url: str):
    decoded_url = urllib.parse.unquote(url)
    validate_surfline_url(decoded_url)

    async def iterfile():
        async with httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
            async with client.stream("GET", decoded_url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="Erro no segmento Surfline Premium")
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="video/mp2t",
        headers={"Access-Control-Allow-Origin": "*"}
    )
