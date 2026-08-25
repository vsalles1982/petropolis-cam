import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import reverse_geocode
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app import Camera, SessionLocal


ARQUIVO_PADRAO = Path(
    "/tmp/tomarigi-world-spots.json"
)

CATEGORIAS = {
    "bousai": "Clima e prevenção",
    "city": "Cidades",
    "coast": "Praias e litoral",
    "nature": "Natureza",
    "other": "Outros",
    "animal": "Animais",
    "train": "Trens e ferrovias",
    "landmark": "Pontos turísticos",
    "airport": "Aeroportos",
}


def criar_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Importa câmeras públicas do Tomarigi "
            "para o Petrópolis Cam."
        )
    )

    parser.add_argument(
        "--arquivo",
        type=Path,
        default=ARQUIVO_PADRAO,
        help=(
            "JSON obtido de /api/world-spots "
            f"(padrão: {ARQUIVO_PADRAO})"
        ),
    )

    parser.add_argument(
        "--limite",
        type=int,
        default=10,
        help=(
            "Quantidade máxima. Use 0 para todas "
            "(padrão seguro: 10)."
        ),
    )

    parser.add_argument(
        "--incluir-offline",
        action="store_true",
        help="Inclui registros que não estão ao vivo.",
    )

    parser.add_argument(
        "--executar",
        action="store_true",
        help=(
            "Grava no banco. Sem esta opção, "
            "o programa apenas simula."
        ),
    )

    return parser


def carregar_spots(
    arquivo: Path,
    incluir_offline: bool,
    limite: int,
):
    if not arquivo.is_file():
        raise SystemExit(
            f"Arquivo não encontrado: {arquivo}"
        )

    with arquivo.open(
        encoding="utf-8"
    ) as stream:
        dados = json.load(stream)

    spots = dados.get("spots")

    if not isinstance(spots, list):
        raise SystemExit(
            "JSON inválido: a lista 'spots' não existe."
        )

    selecionados = [
        spot
        for spot in spots
        if (
            incluir_offline
            or spot.get("is_live") is True
        )
    ]

    if limite < 0:
        raise SystemExit(
            "O limite não pode ser negativo."
        )

    if limite:
        selecionados = selecionados[:limite]

    return selecionados


def enriquecer(spots):
    coordenadas = [
        (
            float(spot["lat"]),
            float(spot["lng"]),
        )
        for spot in spots
    ]

    localizacoes = reverse_geocode.search(
        coordenadas
    )

    momento = datetime.now()
    cameras = []

    for spot, local in zip(
        spots,
        localizacoes,
    ):
        video_id = str(spot["video_id"])
        estado = local.get("state") or None

        cameras.append({
            "slug": (
                "tomarigi-"
                + str(spot["id"])
            ),
            "nome": str(spot["name"]),
            "cidade": (
                local.get("city")
                or "Localização aproximada"
            ),
            "bairro": (
                estado
                or "Não informado"
            ),
            "regiao": estado,
            "pais": local.get("country"),
            "codigo_pais": (
                local.get("country_code")
            ),
            "latitude": float(spot["lat"]),
            "longitude": float(spot["lng"]),
            "categoria": CATEGORIAS.get(
                spot.get("category"),
                "Outros",
            ),
            "fonte": "Tomarigi / YouTube",
            "pagina_oficial": (
                "https://www.youtube.com/watch?v="
                + video_id
            ),
            "stream_url": (
                "https://www.youtube.com/embed/"
                + video_id
            ),
            "tipo_stream": "iframe",
            "autorizada": True,
            "pode_retransmitir": False,
            "online": bool(spot.get("is_live")),
            "ultima_verificacao": momento,
            "origem": "tomarigi",
            "origem_id": str(spot["id"]),
            "video_id": video_id,
        })

    return cameras


def mostrar_simulacao(cameras):
    categorias = Counter(
        camera["categoria"]
        for camera in cameras
    )

    paises = Counter(
        camera["pais"] or "Não identificado"
        for camera in cameras
    )

    print("\nTOMARIGI — SIMULAÇÃO")
    print("=" * 52)
    print(f"Selecionadas: {len(cameras)}")
    print("Banco de dados: não alterado")

    print("\nCategorias:")
    for categoria, quantidade in (
        categorias.most_common()
    ):
        print(
            f"  {quantidade:>5}  {categoria}"
        )

    print("\nPaíses:")
    for pais, quantidade in (
        paises.most_common(15)
    ):
        print(f"  {quantidade:>5}  {pais}")

    print("\nAmostra:")
    for camera in cameras[:5]:
        print(
            "  - "
            f"{camera['nome']} | "
            f"{camera['cidade']}, "
            f"{camera['pais']} | "
            f"{camera['categoria']}"
        )


def gravar(cameras):
    with SessionLocal() as database:
        origens_existentes = set(
            database.scalars(
                select(Camera.origem_id).where(
                    Camera.origem == "tomarigi",
                    Camera.origem_id.is_not(None),
                )
            )
        )

        videos_existentes = set(
            database.scalars(
                select(Camera.video_id).where(
                    Camera.video_id.is_not(None)
                )
            )
        )

        slugs_existentes = set(
            database.scalars(
                select(Camera.slug)
            )
        )

        novas = []
        ignoradas = []

        for dados in cameras:
            motivo = None

            if (
                dados["origem_id"]
                in origens_existentes
            ):
                motivo = "origem_id já cadastrado"
            elif (
                dados["video_id"]
                in videos_existentes
            ):
                motivo = "video_id já cadastrado"
            elif (
                dados["slug"]
                in slugs_existentes
            ):
                motivo = "slug já cadastrado"

            if motivo:
                ignoradas.append(
                    (dados["nome"], motivo)
                )
                continue

            novas.append(Camera(**dados))
            origens_existentes.add(
                dados["origem_id"]
            )
            videos_existentes.add(
                dados["video_id"]
            )
            slugs_existentes.add(
                dados["slug"]
            )

        database.add_all(novas)

        try:
            database.commit()
        except IntegrityError as erro:
            database.rollback()
            raise SystemExit(
                "Importação cancelada e revertida: "
                f"{erro.orig}"
            ) from erro

    print("\nTOMARIGI — RESULTADO")
    print("=" * 52)
    print(f"Cadastradas: {len(novas)}")
    print(f"Ignoradas:   {len(ignoradas)}")

    if ignoradas:
        print("\nPrimeiras ignoradas:")
        for nome, motivo in ignoradas[:10]:
            print(f"  - {nome}: {motivo}")


def main():
    argumentos = criar_parser().parse_args()

    spots = carregar_spots(
        arquivo=argumentos.arquivo,
        incluir_offline=(
            argumentos.incluir_offline
        ),
        limite=argumentos.limite,
    )

    if not spots:
        raise SystemExit(
            "Nenhuma câmera atende aos filtros."
        )

    cameras = enriquecer(spots)
    mostrar_simulacao(cameras)

    if not argumentos.executar:
        print(
            "\nSimulação concluída. "
            "Use --executar para gravar."
        )
        return

    gravar(cameras)


if __name__ == "__main__":
    main()
