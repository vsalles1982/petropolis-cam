import json
import os
import re

import httpx

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/api/geolatlong",
    tags=["GeoLatLong"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_GEO_MODEL = os.getenv(
    "OPENAI_GEO_MODEL",
    "gpt-5.6",
).strip()

MAX_DATA_URL_CHARS = 14_000_000
DATA_URL_PATTERN = re.compile(
    r"^data:image/(jpeg|png|webp);base64,[A-Za-z0-9+/=\r\n]+$"
)


class EstimativaRequest(BaseModel):
    imagem: str = Field(
        min_length=50,
        max_length=MAX_DATA_URL_CHARS,
    )


ESTIMATIVA_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "localizado",
        "local",
        "cidade",
        "regiao",
        "pais",
        "latitude",
        "longitude",
        "confianca",
        "raio_km",
        "resumo",
        "indicios",
        "alternativas",
    ],
    "properties": {
        "localizado": {"type": "boolean"},
        "local": {"type": ["string", "null"]},
        "cidade": {"type": ["string", "null"]},
        "regiao": {"type": ["string", "null"]},
        "pais": {"type": ["string", "null"]},
        "latitude": {"type": ["number", "null"]},
        "longitude": {"type": ["number", "null"]},
        "confianca": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "raio_km": {
            "type": "number",
            "minimum": 0.1,
            "maximum": 20_000,
        },
        "resumo": {"type": "string"},
        "indicios": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string"},
        },
        "alternativas": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "local",
                    "latitude",
                    "longitude",
                    "confianca",
                ],
                "properties": {
                    "local": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "confianca": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
            },
        },
    },
}


PROMPT = """
Você é o motor de estimativa visual do GeoLatLong.

Analise a fotografia e estime onde ela foi tirada usando:
1. elementos visuais, arquitetura, relevo, vegetação, clima, sinalização e texto;
2. reconhecimento de monumentos e lugares públicos;
3. busca web textual e por imagens para comparar candidatos;
4. validação cruzada antes de escolher coordenadas.

Regras:
- Nunca trate uma estimativa como GPS exato.
- Confiança é de 0 a 100 e deve refletir a evidência real.
- O raio deve crescer quando a cena for genérica.
- Se reconhecer um monumento público, use suas coordenadas aproximadas.
- Se não houver pistas suficientes, localizado=false, coordenadas nulas,
  confiança baixa e raio amplo.
- Não identifique pessoas nem tente localizar endereço residencial privado.
  Para residências ou cenas sensíveis, limite o resultado a cidade/região com
  raio amplo.
- Explique os principais indícios de forma curta, em português do Brasil.
""".strip()


def extrair_texto_resposta(dados: dict) -> str:
    for item in dados.get("output", []):
        if item.get("type") != "message":
            continue

        for conteudo in item.get("content", []):
            if conteudo.get("type") == "output_text":
                return conteudo.get("text", "")

    return ""


def extrair_fontes(dados: dict) -> list[dict]:
    fontes = []
    vistos = set()

    for item in dados.get("output", []):
        if item.get("type") != "web_search_call":
            continue

        resultados = item.get("results", [])
        acao = item.get("action", {})
        resultados.extend(acao.get("sources", []))

        for fonte in resultados:
            url = fonte.get("url")
            titulo = fonte.get("title") or fonte.get("caption") or "Fonte"

            if not url or url in vistos:
                continue

            vistos.add(url)
            fontes.append({
                "titulo": titulo,
                "url": url,
            })

            if len(fontes) == 6:
                return fontes

    return fontes


@router.get("/status")
def status_geolatlong():
    return {
        "disponivel": bool(OPENAI_API_KEY),
        "modelo": OPENAI_GEO_MODEL if OPENAI_API_KEY else None,
    }


@router.post("/estimar")
async def estimar_local(dados: EstimativaRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Estimativa visual ainda não configurada. "
                "Defina OPENAI_API_KEY no servidor."
            ),
        )

    if not DATA_URL_PATTERN.fullmatch(dados.imagem):
        raise HTTPException(
            status_code=415,
            detail="Use uma imagem JPEG, PNG ou WebP válida.",
        )

    payload = {
        "model": OPENAI_GEO_MODEL,
        "reasoning": {"effort": "medium"},
        "tools": [
            {
                "type": "web_search",
                "search_content_types": ["image", "text"],
                "image_settings": {
                    "max_results": 6,
                    "caption": True,
                },
            }
        ],
        "include": [
            "web_search_call.results",
            "web_search_call.action.sources",
        ],
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
                    {
                        "type": "input_image",
                        "image_url": dados.imagem,
                        "detail": "high",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "estimativa_geografica",
                "strict": True,
                "schema": ESTIMATIVA_SCHEMA,
            }
        },
        "store": False,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as cliente:
            resposta = await cliente.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

    except httpx.TimeoutException as erro:
        raise HTTPException(
            status_code=504,
            detail="A estimativa demorou além do limite. Tente novamente.",
        ) from erro
    except httpx.HTTPError as erro:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível consultar o serviço de estimativa.",
        ) from erro

    if resposta.status_code == 401:
        raise HTTPException(
            status_code=503,
            detail="A chave da estimativa visual é inválida.",
        )

    if resposta.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Limite temporário da estimativa atingido. Aguarde e tente novamente.",
        )

    if resposta.status_code >= 400:
        detalhe = "O serviço de estimativa recusou a análise."

        try:
            detalhe_api = resposta.json().get("error", {}).get("message")
            if detalhe_api:
                detalhe = detalhe_api
        except ValueError:
            pass

        raise HTTPException(
            status_code=502,
            detail=detalhe,
        )

    resposta_api = resposta.json()
    texto = extrair_texto_resposta(resposta_api)

    if not texto:
        raise HTTPException(
            status_code=502,
            detail="A estimativa não retornou um resultado utilizável.",
        )

    try:
        estimativa = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise HTTPException(
            status_code=502,
            detail="A estimativa retornou dados inválidos.",
        ) from erro

    estimativa["metodo"] = "estimativa_visual"
    estimativa["modelo"] = OPENAI_GEO_MODEL
    estimativa["fontes"] = extrair_fontes(resposta_api)

    return estimativa
