#!/usr/bin/env python3

import argparse
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


CLASSES = (
    "pessoa", "bicicleta", "carro", "moto", "aviao", "onibus", "trem",
    "caminhao", "barco", "semaforo", "hidrante", "placa de pare",
    "parquimetro", "banco", "passaro", "gato", "cachorro", "cavalo",
    "ovelha", "vaca", "elefante", "urso", "zebra", "girafa", "mochila",
    "guarda-chuva", "bolsa", "gravata", "mala", "frisbee", "esquis",
    "snowboard", "bola", "pipa", "taco de beisebol", "luva de beisebol",
    "skate", "prancha", "raquete", "garrafa", "taca", "xicara", "garfo",
    "faca", "colher", "tigela", "banana", "maca", "sanduiche", "laranja",
    "brocolis", "cenoura", "cachorro-quente", "pizza", "donut", "bolo",
    "cadeira", "sofa", "vaso de planta", "cama", "mesa", "vaso sanitario",
    "televisao", "notebook", "mouse", "controle remoto", "teclado",
    "celular", "micro-ondas", "forno", "torradeira", "pia", "geladeira",
    "livro", "relogio", "vaso", "tesoura", "urso de pelucia",
    "secador", "escova de dentes",
)

CORES = [
    (
        int((37 * indice + 70) % 255),
        int((17 * indice + 160) % 255),
        int((29 * indice + 220) % 255),
    )
    for indice in range(len(CLASSES))
]


def argumentos():
    parser = argparse.ArgumentParser(
        description="Prova de conceito YOLOX do Petrópolis Cam"
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("china.mp4"),
        help="Vídeo de entrada",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("vision-poc/saida/china_detectado.mp4"),
        help="Vídeo processado",
    )
    parser.add_argument(
        "--modelo",
        type=Path,
        default=Path(
            "vision-poc/models/object_detection_yolox_2022nov.onnx"
        ),
        help="Modelo YOLOX ONNX",
    )
    parser.add_argument(
        "--cada",
        type=int,
        default=5,
        help="Executar IA a cada N frames",
    )
    parser.add_argument(
        "--confianca",
        type=float,
        default=0.35,
        help="Confiança mínima, entre 0 e 1",
    )
    parser.add_argument(
        "--nms",
        type=float,
        default=0.45,
        help="Limiar de supressão de caixas",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=2,
        help="Threads utilizadas pelo OpenCV",
    )
    parser.add_argument(
        "--limite-segundos",
        type=float,
        default=0,
        help="Limitar teste; zero processa o vídeo inteiro",
    )
    return parser.parse_args()


def validar(config):
    if not config.entrada.is_file():
        raise SystemExit(f"Vídeo não encontrado: {config.entrada}")

    if not config.modelo.is_file():
        raise SystemExit(f"Modelo não encontrado: {config.modelo}")

    if config.cada < 1:
        raise SystemExit("--cada deve ser igual ou maior que 1")

    if config.threads < 1:
        raise SystemExit("--threads deve ser igual ou maior que 1")

    if not 0 < config.confianca < 1:
        raise SystemExit("--confianca deve estar entre 0 e 1")

    if not 0 < config.nms < 1:
        raise SystemExit("--nms deve estar entre 0 e 1")

    config.saida.parent.mkdir(parents=True, exist_ok=True)


def letterbox(frame, tamanho=(640, 640)):
    altura, largura = frame.shape[:2]
    alvo_largura, alvo_altura = tamanho

    escala = min(
        alvo_largura / largura,
        alvo_altura / altura,
    )

    nova_largura = int(largura * escala)
    nova_altura = int(altura * escala)

    redimensionado = cv2.resize(
        frame,
        (nova_largura, nova_altura),
        interpolation=cv2.INTER_LINEAR,
    )

    imagem = np.full(
        (alvo_altura, alvo_largura, 3),
        114,
        dtype=np.uint8,
    )
    imagem[:nova_altura, :nova_largura] = redimensionado

    return imagem, escala


def decodificar_yolox(saida, tamanho=(640, 640)):
    strides = (8, 16, 32)
    grades = []
    strides_expandidos = []

    largura, altura = tamanho

    for stride in strides:
        grade_altura = altura // stride
        grade_largura = largura // stride

        eixo_x, eixo_y = np.meshgrid(
            np.arange(grade_largura),
            np.arange(grade_altura),
        )

        grade = np.stack(
            (eixo_x, eixo_y),
            axis=2,
        ).reshape(1, -1, 2)

        grades.append(grade)

        strides_expandidos.append(
            np.full(
                (*grade.shape[:2], 1),
                stride,
                dtype=np.float32,
            )
        )

    grade_total = np.concatenate(grades, axis=1)
    stride_total = np.concatenate(strides_expandidos, axis=1)

    previsoes = saida.copy()
    previsoes[..., :2] = (
        previsoes[..., :2] + grade_total
    ) * stride_total

    previsoes[..., 2:4] = (
        np.exp(previsoes[..., 2:4]) * stride_total
    )

    return previsoes


def detectar(rede, frame, confianca, limiar_nms):
    imagem, escala = letterbox(frame)

    blob = cv2.dnn.blobFromImage(
        imagem,
        scalefactor=1.0,
        size=(640, 640),
        mean=(0, 0, 0),
        swapRB=False,
        crop=False,
    )

    rede.setInput(blob)
    saida = rede.forward()
    previsoes = decodificar_yolox(saida)[0]

    caixas_centro = previsoes[:, :4]
    probabilidades = (
        previsoes[:, 4:5] * previsoes[:, 5:]
    )

    ids_classes = np.argmax(probabilidades, axis=1)
    confiancas = probabilidades[
        np.arange(len(probabilidades)),
        ids_classes,
    ]

    mascara = confiancas >= confianca

    caixas_centro = caixas_centro[mascara]
    confiancas = confiancas[mascara]
    ids_classes = ids_classes[mascara]

    if len(caixas_centro) == 0:
        return []

    caixas_xywh = []

    for centro_x, centro_y, largura, altura in caixas_centro:
        x = (centro_x - largura / 2) / escala
        y = (centro_y - altura / 2) / escala
        largura = largura / escala
        altura = altura / escala

        caixas_xywh.append(
            [
                int(round(x)),
                int(round(y)),
                int(round(largura)),
                int(round(altura)),
            ]
        )

    indices = cv2.dnn.NMSBoxes(
        caixas_xywh,
        confiancas.tolist(),
        confianca,
        limiar_nms,
    )

    deteccoes = []

    if len(indices) == 0:
        return deteccoes

    altura_frame, largura_frame = frame.shape[:2]

    for indice in np.asarray(indices).reshape(-1):
        x, y, largura, altura = caixas_xywh[int(indice)]

        x1 = max(0, min(x, largura_frame - 1))
        y1 = max(0, min(y, altura_frame - 1))
        x2 = max(0, min(x + largura, largura_frame - 1))
        y2 = max(0, min(y + altura, altura_frame - 1))

        if x2 <= x1 or y2 <= y1:
            continue

        classe_id = int(ids_classes[int(indice)])

        deteccoes.append(
            {
                "classe_id": classe_id,
                "classe": CLASSES[classe_id],
                "confianca": float(confiancas[int(indice)]),
                "caixa": (x1, y1, x2, y2),
            }
        )

    return deteccoes


def desenhar(frame, deteccoes, analisado):
    resultado = frame.copy()
    contagem = Counter(
        deteccao["classe"]
        for deteccao in deteccoes
    )

    for deteccao in deteccoes:
        classe_id = deteccao["classe_id"]
        classe = deteccao["classe"]
        confianca = deteccao["confianca"]
        x1, y1, x2, y2 = deteccao["caixa"]

        cor = CORES[classe_id]
        rotulo = f"{classe} {confianca:.0%}"

        cv2.rectangle(
            resultado,
            (x1, y1),
            (x2, y2),
            cor,
            2,
        )

        (largura_texto, altura_texto), _ = cv2.getTextSize(
            rotulo,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            1,
        )

        topo = max(y1, altura_texto + 10)

        cv2.rectangle(
            resultado,
            (x1, topo - altura_texto - 9),
            (x1 + largura_texto + 8, topo),
            cor,
            -1,
        )

        cv2.putText(
            resultado,
            rotulo,
            (x1 + 4, topo - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (15, 15, 15),
            1,
            cv2.LINE_AA,
        )

    itens = [
        f"{nome}: {quantidade}"
        for nome, quantidade in contagem.most_common(6)
    ]

    resumo = " | ".join(itens) if itens else "Nenhum objeto detectado"

    cv2.rectangle(
        resultado,
        (0, 0),
        (resultado.shape[1], 42),
        (18, 22, 28),
        -1,
    )

    cv2.putText(
        resultado,
        resumo,
        (12, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (80, 220, 160),
        2,
        cv2.LINE_AA,
    )

    if not analisado:
        cv2.putText(
            resultado,
            "deteccao mantida",
            (resultado.shape[1] - 180, resultado.shape[0] - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )

    return resultado, contagem


def criar_gravador(caminho, fps, largura, altura):
    codecs = ("avc1", "mp4v")

    for nome_codec in codecs:
        codec = cv2.VideoWriter_fourcc(*nome_codec)
        gravador = cv2.VideoWriter(
            str(caminho),
            codec,
            fps,
            (largura, altura),
        )

        if gravador.isOpened():
            print(f"Codec de saída: {nome_codec}")
            return gravador

        gravador.release()

    raise SystemExit("Não foi possível criar o vídeo de saída")


def executar(config):
    cv2.setNumThreads(config.threads)

    print("Carregando YOLOX...")
    rede = cv2.dnn.readNetFromONNX(str(config.modelo))
    rede.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)

    captura = cv2.VideoCapture(str(config.entrada))

    if not captura.isOpened():
        raise SystemExit(
            f"Não foi possível abrir o vídeo: {config.entrada}"
        )

    fps = captura.get(cv2.CAP_PROP_FPS)
    largura = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))

    if fps <= 0:
        fps = 25.0

    limite_frames = total_frames

    if config.limite_segundos > 0:
        limite_frames = min(
            total_frames,
            int(config.limite_segundos * fps),
        )

    gravador = criar_gravador(
        config.saida,
        fps,
        largura,
        altura,
    )

    print(f"Entrada: {config.entrada}")
    print(f"Resolução: {largura}x{altura}")
    print(f"FPS: {fps:.2f}")
    print(f"Frames previstos: {limite_frames}")
    print(f"IA: um frame a cada {config.cada}")
    print(f"Threads: {cv2.getNumThreads()}")
    print("Processando...")

    inicio_total = time.perf_counter()
    frame_id = 0
    inferencias = 0
    tempo_inferencias = 0.0
    ultimas_deteccoes = []
    maximos = Counter()

    try:
        while frame_id < limite_frames:
            sucesso, frame = captura.read()

            if not sucesso:
                break

            analisado = (
                frame_id == 0
                or frame_id % config.cada == 0
            )

            if analisado:
                inicio_ia = time.perf_counter()

                ultimas_deteccoes = detectar(
                    rede,
                    frame,
                    config.confianca,
                    config.nms,
                )

                tempo_inferencias += (
                    time.perf_counter() - inicio_ia
                )
                inferencias += 1

            frame_saida, contagem = desenhar(
                frame,
                ultimas_deteccoes,
                analisado,
            )

            for classe, quantidade in contagem.items():
                maximos[classe] = max(
                    maximos[classe],
                    quantidade,
                )

            gravador.write(frame_saida)
            frame_id += 1

            if frame_id % 100 == 0 or frame_id == limite_frames:
                percentual = (
                    frame_id / limite_frames * 100
                    if limite_frames
                    else 0
                )
                print(
                    f"\rFrames: {frame_id}/{limite_frames} "
                    f"({percentual:.1f}%)",
                    end="",
                    flush=True,
                )

    finally:
        captura.release()
        gravador.release()

    duracao = time.perf_counter() - inicio_total
    media_ia = (
        tempo_inferencias / inferencias
        if inferencias
        else 0
    )

    print("\n")
    print("Processamento concluído")
    print(f"Frames gravados: {frame_id}")
    print(f"Inferências: {inferencias}")
    print(f"Tempo total: {duracao:.2f} segundos")
    print(f"Média por inferência: {media_ia:.3f} segundos")

    if duracao > 0:
        print(
            f"Velocidade total: {frame_id / duracao:.2f} FPS"
        )

    if maximos:
        print("Máximo observado por classe:")

        for classe, quantidade in maximos.most_common():
            print(f"  {classe}: {quantidade}")
    else:
        print("Nenhum objeto ultrapassou a confiança mínima.")

    print(f"Vídeo gerado: {config.saida}")


def main():
    config = argumentos()
    validar(config)
    executar(config)


if __name__ == "__main__":
    main()
