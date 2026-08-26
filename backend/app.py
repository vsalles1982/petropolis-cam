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

app.mount(
    "/vision-demo",
    StaticFiles(directory=VISION_OUTPUT_DIR),
    name="vision-demo",
)


app.mount(
    "/",
    StaticFiles(
        directory=FRONTEND_DIR,
        html=True,
    ),
    name="frontend",
)
