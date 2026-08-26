# Visão computacional — Petrópolis Cam

Prova de conceito isolada para detecção de objetos em vídeos e câmeras autorizadas, usando YOLOX no formato ONNX e OpenCV DNN.

## Recursos

- execução local em CPU;
- sem PyTorch e sem CUDA;
- limite configurável de threads;
- detecção das 80 classes COCO;
- caixas, rótulos e confiança;
- contagem de objetos;
- processamento espaçado de frames;
- vídeo anotado como saída;
- integração visual preparada no player do Petrópolis Cam.

## Limitações

O detector não acessa frames incorporados em iframes do YouTube.

A opção de monitoramento por IA somente deve aparecer para fontes diretas, autorizadas e explicitamente marcadas como compatíveis.

Fontes previstas:

- HLS;
- RTSP;
- MediaMTX;
- arquivos locais;
- imagens oficiais atualizadas.

## Instalação

```bash
cd "$HOME/petropolis-cam"

python -m venv vision-poc/.venv

source vision-poc/.venv/bin/activate

python -m pip install --upgrade pip

python -m pip install -r vision-poc/requirements.txt
