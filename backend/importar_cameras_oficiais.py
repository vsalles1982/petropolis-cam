import time
import unicodedata

import httpx


API_CAMERAS = "http://127.0.0.1:8002/api/cameras"

PAGINA_OFICIAL = (
    "https://www.youtube.com/watch?v=wP-YhO7-OAI"
)

USER_AGENT = (
    "PetropolisCam/0.2 "
    "(catalogo comunitario de fontes publicas)"
)


CAMERAS = [
    {
        "nome": "Rua Paulo Barbosa / Terminal Centro",
        "bairro": "Centro",
        "busca": (
            "Terminal Centro, Rua Paulo Barbosa, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Praça da Inconfidência",
        "bairro": "Centro",
        "busca": (
            "Praça da Inconfidência, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Rua do Imperador / Rua Dr. Nelson de Sá Earp",
        "bairro": "Centro",
        "busca": (
            "Rua Doutor Nelson de Sá Earp, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Rua do Imperador / Rua Paulo Barbosa",
        "bairro": "Centro",
        "busca": (
            "Rua do Imperador com Rua Paulo Barbosa, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Obelisco de Petrópolis",
        "bairro": "Centro",
        "busca": (
            "Obelisco de Petrópolis, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Praça da Águia",
        "bairro": "Centro",
        "busca": (
            "Praça Visconde de Mauá, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Início da Rua Teresa",
        "bairro": "Centro",
        "busca": (
            "Rua Teresa, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Catedral São Pedro de Alcântara",
        "bairro": "Centro",
        "busca": (
            "Catedral São Pedro de Alcântara, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Rua Treze de Maio",
        "bairro": "Centro",
        "busca": (
            "Rua Treze de Maio, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Entrada da Rua Mosela",
        "bairro": "Mosela",
        "busca": (
            "Rua Mosela, Mosela, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Rua Montecaseros",
        "bairro": "Centro",
        "busca": (
            "Rua Montecaseros, Centro, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Hospital Santa Teresa",
        "bairro": "Bingen",
        "busca": (
            "Hospital Santa Teresa, Bingen, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Praça de Corrêas",
        "bairro": "Corrêas",
        "busca": (
            "Praça de Corrêas, Corrêas, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Trevo de Bonsucesso",
        "bairro": "Bonsucesso",
        "busca": (
            "Trevo de Bonsucesso, Bonsucesso, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "DPO de Pedro do Rio",
        "bairro": "Pedro do Rio",
        "busca": (
            "DPO Pedro do Rio, Pedro do Rio, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
    {
        "nome": "Centro da Posse",
        "bairro": "Posse",
        "busca": (
            "Centro, Posse, "
            "Petrópolis, Rio de Janeiro, Brasil"
        ),
    },
]


COORDENADAS_FALLBACK = {
    "Rua Paulo Barbosa / Terminal Centro": (
        -22.5089,
        -43.1712,
    ),
    "Praça da Inconfidência": (
        -22.5095,
        -43.1730,
    ),
    "Rua do Imperador / Rua Dr. Nelson de Sá Earp": (
        -22.5079,
        -43.1770,
    ),
    "Rua do Imperador / Rua Paulo Barbosa": (
        -22.5090,
        -43.1725,
    ),
    "Obelisco de Petrópolis": (
        -22.5091,
        -43.1762,
    ),
    "Praça da Águia": (
        -22.5081,
        -43.1776,
    ),
    "Início da Rua Teresa": (
        -22.5120,
        -43.1740,
    ),
    "Catedral São Pedro de Alcântara": (
        -22.5058,
        -43.1795,
    ),
    "Rua Treze de Maio": (
        -22.5066,
        -43.1784,
    ),
    "Entrada da Rua Mosela": (
        -22.5055,
        -43.1930,
    ),
    "Rua Montecaseros": (
        -22.5103,
        -43.1832,
    ),
    "Hospital Santa Teresa": (
        -22.5179,
        -43.2014,
    ),
    "Praça de Corrêas": (
        -22.4468,
        -43.1390,
    ),
    "Trevo de Bonsucesso": (
        -22.4210,
        -43.1260,
    ),
    "DPO de Pedro do Rio": (
        -22.3345,
        -43.1310,
    ),
    "Centro da Posse": (
        -22.2290,
        -43.1040,
    ),
}


def criar_slug(texto):
    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = texto.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    caracteres = []

    for caractere in texto.lower():
        if caractere.isalnum():
            caracteres.append(caractere)
        else:
            caracteres.append("-")

    slug = "".join(caracteres)

    while "--" in slug:
        slug = slug.replace("--", "-")

    return "cimop-" + slug.strip("-")


def buscar_coordenadas(cliente, camera):
    try:
        resposta = cliente.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": camera["busca"],
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "br",
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "pt-BR",
            },
            timeout=15.0,
        )

        resposta.raise_for_status()
        resultados = resposta.json()

        if resultados:
            return (
                float(resultados[0]["lat"]),
                float(resultados[0]["lon"]),
                "OpenStreetMap",
            )

    except (
        httpx.HTTPError,
        ValueError,
        KeyError,
        IndexError,
    ):
        pass

    latitude, longitude = COORDENADAS_FALLBACK[
        camera["nome"]
    ]

    return latitude, longitude, "aproximada"


def cadastrar_camera(
    cliente,
    camera,
    latitude,
    longitude,
):
    dados = {
        "slug": criar_slug(camera["nome"]),
        "nome": camera["nome"],
        "cidade": "Petrópolis",
        "bairro": camera["bairro"],
        "latitude": latitude,
        "longitude": longitude,
        "categoria": "CIMOP",
        "fonte": "Prefeitura de Petrópolis / CIMOP",
        "pagina_oficial": PAGINA_OFICIAL,
        "stream_url": None,
        "tipo_stream": "pagina_oficial",
        "autorizada": True,
        "pode_retransmitir": False,
    }

    return cliente.post(
        API_CAMERAS,
        json=dados,
        timeout=10.0,
    )


def main():
    cadastradas = 0
    existentes = 0
    erros = 0

    with httpx.Client() as cliente:
        for numero, camera in enumerate(
            CAMERAS,
            start=1,
        ):
            latitude, longitude, origem = (
                buscar_coordenadas(
                    cliente,
                    camera,
                )
            )

            resposta = cadastrar_camera(
                cliente,
                camera,
                latitude,
                longitude,
            )

            if resposta.status_code == 201:
                cadastradas += 1
                resultado = "CADASTRADA"

            elif resposta.status_code == 409:
                existentes += 1
                resultado = "JÁ EXISTE"

            else:
                erros += 1
                resultado = (
                    f"ERRO {resposta.status_code}"
                )

            print(
                f"[{numero:02d}/16] "
                f"{resultado}: "
                f"{camera['nome']} "
                f"({origem})"
            )

            
            #  O Nominatim exige intervalo entre consultas.
             
            time.sleep(1.1)

    print()
    print("Importação concluída")
    print(f"Cadastradas: {cadastradas}")
    print(f"Já existentes: {existentes}")
    print(f"Erros: {erros}")


if __name__ == "__main__":
    main()
