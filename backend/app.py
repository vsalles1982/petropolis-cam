import httpx

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    String,
    create_engine,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from backend.geolatlong_api import (
    router as geolatlong_router,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_FILE = PROJECT_DIR / "data" / "cameras.db"
FRONTEND_DIR = PROJECT_DIR / "frontend"
VISION_OUTPUT_DIR = PROJECT_DIR / "vision-poc" / "saida"
VISION_DEMO_FILE = (
    VISION_OUTPUT_DIR
    / "china_detectado_completo.mp4"
)

MEDIAMTX_API = (
    "http://127.0.0.1:9997/v3/paths/list"
)

MEDIAMTX_USER = "petropolis_api"
MEDIAMTX_PASSWORD = "petropolis-local-api"

DATABASE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

engine = create_engine(
    f"sqlite:///{DATABASE_FILE}",
    connect_args={
        "check_same_thread": False,
    },
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )

    nome: Mapped[str] = mapped_column(
        String(200),
    )

    cidade: Mapped[str] = mapped_column(
        String(100),
        default="Petrópolis",
    )

    bairro: Mapped[str] = mapped_column(
        String(100),
    )

    latitude: Mapped[float] = mapped_column(
        Float,
    )

    longitude: Mapped[float] = mapped_column(
        Float,
    )

    categoria: Mapped[str] = mapped_column(
        String(50),
    )

    fonte: Mapped[str] = mapped_column(
        String(200),
    )

    regiao: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    pais: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    codigo_pais: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
    )

    origem: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    origem_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    video_id: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    pagina_oficial: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
        )
    )

    stream_url: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
        )
    )

    tipo_stream: Mapped[str] = mapped_column(
        String(30),
        default="pagina_oficial",
    )

    autorizada: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    pode_retransmitir: Mapped[bool] = (
        mapped_column(
            Boolean,
            default=False,
        )
    )

    online: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    ultima_verificacao: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )


class CameraBase(BaseModel):
    slug: str
    nome: str
    cidade: str = "Petrópolis"
    bairro: str
    latitude: float
    longitude: float
    categoria: str
    fonte: str
    regiao: str | None = None
    pais: str | None = None
    codigo_pais: str | None = None
    origem: str | None = None
    origem_id: str | None = None
    video_id: str | None = None
    pagina_oficial: str | None = None
    stream_url: str | None = None
    tipo_stream: str = "pagina_oficial"
    autorizada: bool = False
    pode_retransmitir: bool = False


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    slug: str | None = None
    nome: str | None = None
    cidade: str | None = None
    bairro: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    categoria: str | None = None
    fonte: str | None = None
    regiao: str | None = None
    pais: str | None = None
    codigo_pais: str | None = None
    origem: str | None = None
    origem_id: str | None = None
    video_id: str | None = None
    pagina_oficial: str | None = None
    stream_url: str | None = None
    tipo_stream: str | None = None
    autorizada: bool | None = None
    pode_retransmitir: bool | None = None


class CameraResponse(CameraBase):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    online: bool
    ultima_verificacao: datetime | None


def get_database():
    database = SessionLocal()

    try:
        yield database
    finally:
        database.close()


def create_initial_camera():
    with SessionLocal() as database:
        existente = database.scalar(
            select(Camera).where(
                Camera.slug == "teste"
            )
        )

        if existente is not None:
            return

        camera = Camera(
            slug="teste",
            nome="Transmissão de teste",
            cidade="Petrópolis",
            bairro="Centro",
            latitude=-22.5112,
            longitude=-43.1779,
            categoria="teste",
            fonte="Projeto Petrópolis Cam",
            pagina_oficial=None,
            stream_url=(
                "http://localhost:8889/teste"
            ),
            tipo_stream="webrtc",
            autorizada=True,
            pode_retransmitir=True,
            online=False,
        )

        database.add(camera)
        database.commit()


def obter_caminhos_mediamtx():
    try:
        resposta = httpx.get(
            MEDIAMTX_API,
            auth=(
                MEDIAMTX_USER,
                MEDIAMTX_PASSWORD,
            ),
            timeout=2.0,
        )

        resposta.raise_for_status()
        dados = resposta.json()

        return {
            item["name"]
            for item in dados.get("items", [])
            if item.get("ready", False)
        }

    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
    ):
        return set()


def sincronizar_status_mediamtx(
    database: Session,
):
    caminhos_ativos = (
        obter_caminhos_mediamtx()
    )

    cameras = database.scalars(
        select(Camera)
    ).all()

    momento = datetime.now()

    for camera in cameras:
        
         # Fontes externas não dependem do MediaMTX.
         # Apenas streams retransmitidos são sincronizados.
         
        if not camera.pode_retransmitir:
            continue

        novo_status = (
            camera.slug in caminhos_ativos
        )

        if camera.online != novo_status:
            camera.online = novo_status
            camera.ultima_verificacao = momento

    database.commit()


def obter_camera_ou_404(
    camera_id: int,
    database: Session,
):
    camera = database.get(
        Camera,
        camera_id,
    )

    if camera is None:
        raise HTTPException(
            status_code=404,
            detail="Câmera não encontrada",
        )

    return camera


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    create_initial_camera()

    yield


app = FastAPI(
    title="Petrópolis Cam",
    description=(
        "Catálogo de câmeras públicas "
        "e autorizadas"
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:8002",
        "http://127.0.0.1:8002",
    ],
    allow_methods=[
        "GET",
        "POST",
        "PATCH",
        "DELETE",
    ],
    allow_headers=["*"],
)

app.include_router(geolatlong_router)


@app.get("/api/saude")
def verificar_saude():
    mediamtx = False

    try:
        resposta = httpx.get(
            MEDIAMTX_API,
            auth=(
                MEDIAMTX_USER,
                MEDIAMTX_PASSWORD,
            ),
            timeout=2.0,
        )

        mediamtx = (
            resposta.status_code == 200
        )

    except httpx.HTTPError:
        mediamtx = False

    return {
        "status": "funcionando",
        "projeto": "Petrópolis Cam",
        "versao": "0.3.0",
        "mediamtx": mediamtx,
    }


@app.get(
    "/api/cameras",
    response_model=list[CameraResponse],
)
def listar_cameras(
    database: Session = Depends(
        get_database
    ),
):
    sincronizar_status_mediamtx(
        database
    )

    return list(
        database.scalars(
            select(Camera).order_by(
                Camera.nome
            )
        )
    )


@app.get(
    "/api/cameras/{camera_id}",
    response_model=CameraResponse,
)
def obter_camera(
    camera_id: int,
    database: Session = Depends(
        get_database
    ),
):
    sincronizar_status_mediamtx(
        database
    )

    return obter_camera_ou_404(
        camera_id,
        database,
    )


@app.post(
    "/api/cameras",
    response_model=CameraResponse,
    status_code=201,
)
def cadastrar_camera(
    dados: CameraCreate,
    database: Session = Depends(
        get_database
    ),
):
    existente = database.scalar(
        select(Camera).where(
            Camera.slug == dados.slug
        )
    )

    if existente is not None:
        raise HTTPException(
            status_code=409,
            detail="Slug já cadastrado",
        )

    camera = Camera(
        **dados.model_dump()
    )

    database.add(camera)
    database.commit()
    database.refresh(camera)

    return camera


@app.patch(
    "/api/cameras/{camera_id}",
    response_model=CameraResponse,
)
def editar_camera(
    camera_id: int,
    dados: CameraUpdate,
    database: Session = Depends(
        get_database
    ),
):
    camera = obter_camera_ou_404(
        camera_id,
        database,
    )

    alteracoes = dados.model_dump(
        exclude_unset=True,
    )

    novo_slug = alteracoes.get("slug")

    if (
        novo_slug is not None
        and novo_slug != camera.slug
    ):
        slug_existente = database.scalar(
            select(Camera).where(
                Camera.slug == novo_slug
            )
        )

        if slug_existente is not None:
            raise HTTPException(
                status_code=409,
                detail="Slug já cadastrado",
            )

    for campo, valor in alteracoes.items():
        setattr(
            camera,
            campo,
            valor,
        )

    database.commit()
    database.refresh(camera)

    return camera


@app.delete(
    "/api/cameras/{camera_id}",
)
def excluir_camera(
    camera_id: int,
    database: Session = Depends(
        get_database
    ),
):
    camera = obter_camera_ou_404(
        camera_id,
        database,
    )

    nome = camera.nome

    database.delete(camera)
    database.commit()

    return {
        "excluida": True,
        "id": camera_id,
        "nome": nome,
    }


@app.patch(
    "/api/cameras/{camera_id}/status",
    response_model=CameraResponse,
)
def atualizar_status(
    camera_id: int,
    online: bool,
    database: Session = Depends(
        get_database
    ),
):
    camera = obter_camera_ou_404(
        camera_id,
        database,
    )

    camera.online = online
    camera.ultima_verificacao = (
        datetime.now()
    )

    database.commit()
    database.refresh(camera)

    return camera


@app.get("/api/vision/demo")
def obter_demonstracao_vision():
    """Informa se o vídeo local da prova de conceito está disponível."""
    disponivel = VISION_DEMO_FILE.is_file()

    return {
        "disponivel": disponivel,
        "modo": "demonstracao",
        "rotulo": "Demonstração local — china.mp4",
        "video_url": (
            "/vision-demo/china_detectado_completo.mp4"
            if disponivel
            else None
        ),
    }


VISION_OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)



# ==========================================
# PROXY DE MÍDIA (TfL e outros)
# ==========================================
from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx

@app.get("/api/proxy")
async def proxy_stream(url: str, request: Request):
    headers = {"User-Agent": "Mozilla/5.0"}
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]

    async def stream_generator():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, headers=headers, follow_redirects=True, timeout=30.0) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    async with httpx.AsyncClient() as client:
        head_resp = await client.head(url, headers=headers, follow_redirects=True)
        response_headers = {}
        if "content-length" in head_resp.headers:
            response_headers["Content-Length"] = head_resp.headers["content-length"]
        if "accept-ranges" in head_resp.headers:
            response_headers["Accept-Ranges"] = head_resp.headers["accept-ranges"]

    media_type = "video/mp4" if ".mp4" in url.lower() else "image/jpeg"
    return StreamingResponse(stream_generator(), media_type=media_type, headers=response_headers)



# ==========================================
# PROXY HLS (Para DER-SP e outros)
# ==========================================
from fastapi import Request
from fastapi.responses import Response
import httpx


# ==========================================
from fastapi import Request
from fastapi.responses import Response
import httpx
import re

# ==========================================
# EXTRATOR E PROXY DE STREAM UTIC (Corrigido)
# ==========================================
from fastapi import Request
from fastapi.responses import Response
import httpx
import re

@app.get("/api/utic/stream")
async def utic_stream(cctvid: str):
    url_player = f"https://www.utic.go.kr/jsp/map/cctvStream.jsp?cctvid={cctvid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.utic.go.kr/map/map.do",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url_player, headers=headers, follow_redirects=True, timeout=20)
            html = resp.text
    except Exception as e:
        return Response(content=f"Erro ao acessar UTIC: {e}", status_code=502)

    # A MÁGICA ACONTECE AQUI: Regex que captura TUDO até o fim da string (incluindo ?token=...)
    match = re.search(r'(https?://[^"\s]+)', html)
    
    if not match:
        return Response(content="Link não encontrado no HTML.", status_code=502)
        
    # O link pode ter pego um pedaço de script, então limpamos
    m3u8_url = match.group(1).strip().rstrip("'").rstrip('"')
    
    # Se o link não terminar em m3u8 (por causa de um parâmetro depois), ainda tentamos
    if ".m3u8" not in m3u8_url:
        return Response(content=f"URL inválida: {m3u8_url}", status_code=502)

    try:
        async with httpx.AsyncClient() as client:
            resp_m3u8 = await client.get(m3u8_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            resp_m3u8.raise_for_status()
            conteudo = resp_m3u8.text
    except Exception as e:
        return Response(content=f"Erro ao baixar m3u8 ({m3u8_url}): {e}", status_code=502)

    from urllib.parse import urljoin, quote
    base_url = m3u8_url.rsplit('/', 1)[0] + '/'
    linhas_novas = []
    for linha in conteudo.split('\n'):
        linha = linha.strip()
        if linha and not linha.startswith('#'):
            url_absoluta = urljoin(base_url, linha)
            linhas_novas.append(f"/api/proxy?url={quote(url_absoluta, safe='')}")
        else:
            linhas_novas.append(linha)

    return Response(
        content='\n'.join(linhas_novas),
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/api/utic/stream")
async def utic_stream(cctvid: str):
    url_player = f"https://www.utic.go.kr/jsp/map/cctvStream.jsp?cctvid={cctvid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.utic.go.kr/map/map.do",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url_player, headers=headers, follow_redirects=True, timeout=20)
            html = resp.text
    except Exception as e:
        return Response(content=f"Erro ao acessar UTIC: {e}", status_code=502)

    match = re.search(r'(https?://[^"\s\']+\.m3u8[^"\s\']*)', html)
    
    if not match:
        return Response(content="Link .m3u8 não encontrado no HTML.", status_code=502)
        
    m3u8_url = match.group(1)

    try:
        async with httpx.AsyncClient() as client:
            resp_m3u8 = await client.get(m3u8_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            resp_m3u8.raise_for_status()
            conteudo = resp_m3u8.text
    except Exception as e:
        return Response(content=f"Erro ao baixar m3u8: {e}", status_code=502)

    from urllib.parse import urljoin, quote
    base_url = m3u8_url.rsplit('/', 1)[0] + '/'
    linhas_novas = []
    for linha in conteudo.split('\n'):
        linha = linha.strip()
        if linha and not linha.startswith('#'):
            url_absoluta = urljoin(base_url, linha)
            linhas_novas.append(f"/api/proxy?url={quote(url_absoluta, safe='')}")
        else:
            linhas_novas.append(linha)

    return Response(
        content='\n'.join(linhas_novas),
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/api/proxy/hls")
async def proxy_hls(url: str):
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://200.144.30.103:8084/"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            resp.raise_for_status()
            conteudo = resp.text
    except Exception as e:
        return Response(content=f"Erro: {e}", status_code=502)

    base_url = url.rsplit('/', 1)[0] + '/'
    linhas_novas = []
    for linha in conteudo.split('\n'):
        linha = linha.strip()
        if linha and not linha.startswith('#'):
            url_absoluta = linha if linha.startswith('http') else f"{base_url}{linha}"
            if '.m3u8' in url_absoluta:
                linhas_novas.append(f"/api/proxy/hls?url={url_absoluta}")
            else:
                linhas_novas.append(f"/api/proxy?url={url_absoluta}")
        else:
            linhas_novas.append(linha)

    return Response(content='\n'.join(linhas_novas), media_type="application/vnd.apple.mpegurl", headers={"Access-Control-Allow-Origin": "*"})




# ==========================================
# MOUNTS (Vision Demo e Frontend)
# ==========================================
VISION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/proxy/mjpeg")
async def proxy_mjpeg(url: str):
    import httpx
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    parts = url.split("/")
    referer = f"{parts}//{parts}/" if len(parts) > 2 else url
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": referer
    }
    client = httpx.AsyncClient(verify=False, follow_redirects=True, timeout=15.0)
    req = client.build_request("GET", url, headers=headers)
    resp = await client.send(req, stream=True)

    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=resp.status_code, detail="Erro no stream MJPEG")

    async def iter_chunks():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=8192):
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    content_type = resp.headers.get("content-type", "multipart/x-mixed-replace")
    return StreamingResponse(
        iter_chunks(),
        media_type=content_type,
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
    )


import re as _re
import time as _time
from urllib.parse import urljoin as _urljoin, quote as _quote
from fastapi import Response as _Response
from curl_cffi import requests as _cffi_requests

_EC_CACHE = {}


import time as _mc_time
import re as _mc_re
from urllib.parse import urljoin as _mc_urljoin, quote as _mc_quote
from curl_cffi import requests as _mc_req
from fastapi import HTTPException as _mc_HTTP
from fastapi.responses import Response as _mc_Resp

_MC_SLASH = chr(47)
_MC_BASE = "https:" + _MC_SLASH + _MC_SLASH + "maaxcam.com.br"
_MC_FN = "fb4e84860f7bc65c17b932c658b18aa7050a6f470ce3fd23a5b0b9f05b160a4d"
_MC_CACHE = {}

def _mc_get_hls(slug: str) -> str:
    now = _mc_time.time()
    cached = _MC_CACHE.get(slug)
    if cached and (now - cached[1]) < 300:
        return cached[0]
    hdr = {
        "Accept": "application/json",
        "x-tsr-serverFn": "true",
        "Origin": _MC_BASE,
        "Referer": _MC_BASE + "/camera/" + slug,
    }
    payload = {
        "t": {
            "t": 10,
            "i": 0,
            "p": {
                "k": ["data"],
                "v": [{
                    "t": 10,
                    "i": 1,
                    "p": {"k": ["slug"], "v": [{"t": 1, "s": slug}]},
                }],
            },
        },
        "f": 63,
        "m": [],
    }
    r = _mc_req.post(_MC_BASE + "/_serverFn/" + _MC_FN, json=payload, headers=hdr, impersonate="chrome", timeout=15)
    m = _mc_re.search(r'"s":"(https?:[^"]+\.m3u8[^"]*)"', r.text)
    if not m:
        raise _mc_HTTP(status_code=502, detail="Maaxcam stream indisponivel")
    hls_url = m.group(1).replace("\\/", "/")
    _MC_CACHE[slug] = (hls_url, now)
    return hls_url

@app.get("/api/maaxcam/seg")
def maaxcam_seg(url: str):
    hdr = {"Referer": _MC_BASE + "/", "Origin": _MC_BASE}
    r = _mc_req.get(url, headers=hdr, impersonate="chrome", timeout=15)
    if r.status_code != 200:
        raise _mc_HTTP(status_code=r.status_code, detail="Erro segmento Maaxcam")
    ct = r.headers.get("content-type", "video/mp2t")
    if "mpegurl" in ct.lower() or url.split("?")[0].endswith(".m3u8"):
        lines = []
        for line in r.text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                abs_u = _mc_urljoin(url, s)
                lines.append(f"/api/maaxcam/seg?url={_mc_quote(abs_u, safe='')}")
            else:
                lines.append(line)
        return _mc_Resp(content="\n".join(lines), media_type="application/vnd.apple.mpegurl")
    return _mc_Resp(content=r.content, media_type=ct)

@app.get("/api/maaxcam/stream.m3u8")
def maaxcam_master(slug: str):
    hls_url = _mc_get_hls(slug)
    hdr = {"Referer": _MC_BASE + "/", "Origin": _MC_BASE}
    r = _mc_req.get(hls_url, headers=hdr, impersonate="chrome", timeout=15)
    if r.status_code != 200:
        _MC_CACHE.pop(slug, None)
        hls_url = _mc_get_hls(slug)
        r = _mc_req.get(hls_url, headers=hdr, impersonate="chrome", timeout=15)
    if r.status_code != 200:
        raise _mc_HTTP(status_code=r.status_code, detail="Erro playlist Maaxcam")
    lines = []
    for line in r.text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            abs_u = _mc_urljoin(hls_url, s)
            lines.append(f"/api/maaxcam/seg?url={_mc_quote(abs_u, safe='')}")
        else:
            lines.append(line)
    return _mc_Resp(content="\n".join(lines), media_type="application/vnd.apple.mpegurl")

@app.get("/api/earthcam/seg")
async def earthcam_segment(url: str):
    headers = {
        "Referer": "https://earthcam.com",
        "Origin": "https://earthcam.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=15.0) as client:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Erro EarthCam seg")
        ct = r.headers.get("content-type", "application/octet-stream")
        if "mpegurl" in ct.lower() or url.split("?")[0].endswith(".m3u8"):
            lines = []
            for line in r.text.splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    abs_u = _urljoin(url, s)
                    lines.append(f"/api/earthcam/seg?url={_quote(abs_u, safe='')}")
                else:
                    lines.append(line)
            return _Response("\n".join(lines), media_type="application/vnd.apple.mpegurl", headers={"Access-Control-Allow-Origin": "*"})
        return _Response(r.content, media_type=ct, headers={"Access-Control-Allow-Origin": "*"})

@app.get("/api/earthcam/stream.m3u8")
def earthcam_master(url: str):
    now = _time.time()
    cached = _EC_CACHE.get(url)
    if cached and (now - cached[1]) < 900:
        stream_url = cached[0]
    else:
        r = _cffi_requests.get(url, impersonate="chrome", timeout=15)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Falha ao ler pagina EarthCam")
        m_cam = _re.search(r"[?&]cam=([a-zA-Z0-9_-]+)", url)
        cam_key = m_cam.group(1) if m_cam else None
        m_json = _re.search(r"json_base\s*=\s*(\{.*\});", r.text)
        stream_url = None
        if m_json:
            import json as _json
            try:
                jb = _json.loads(m_json.group(1))
                cams = jb.get("cam", {})
                target = cams.get(cam_key) if (cam_key and cam_key in cams) else next(iter(cams.values()), {})
                stream_url = (target.get("stream") or "").replace("\\/", "/")
            except Exception:
                pass
        if not stream_url:
            m_st = _re.search(r"\"stream\"\s*:\s*\"(https?:\\/\\/[^\"]+\.m3u8[^\"]*)\"", r.text)
            if m_st:
                stream_url = m_st.group(1).replace("\\/", "/")
        if not stream_url:
            raise HTTPException(status_code=404, detail="Stream EarthCam nao encontrado")
        _EC_CACHE[url] = (stream_url, now)

    headers = {
        "Referer": "https://earthcam.com",
        "Origin": "https://earthcam.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    resp = _cffi_requests.get(stream_url, headers=headers, impersonate="chrome", timeout=15)
    if resp.status_code != 200:
        _EC_CACHE.pop(url, None)
        raise HTTPException(status_code=resp.status_code, detail="Playlist EarthCam indisponivel")

    lines = []
    for line in resp.text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            abs_u = _urljoin(stream_url, s)
            lines.append(f"/api/earthcam/seg?url={_quote(abs_u, safe='')}")
        else:
            lines.append(line)

    return _Response(
        "\n".join(lines),
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
    )

from backend.clima_proxy import router as clima_router
app.include_router(clima_router)

from backend.waves_proxy import router as waves_router
app.include_router(waves_router)

app.mount(
    "/vision-demo",
    StaticFiles(directory=VISION_OUTPUT_DIR),
    name="vision-demo",
)

app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)
