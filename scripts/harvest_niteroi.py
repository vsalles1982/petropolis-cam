#!/usr/bin/env python3
import sys
import httpx
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

BASE_URL = "https://appnittrans.niteroi.rj.gov.br:8888"

def testar_id(cam_id: str):
    """Testa se o ID tem um vídeo válido."""
    url = f"{BASE_URL}/{cam_id}/last_video.mp4"
    try:
        r = httpx.head(url, timeout=5, verify=False)
        if r.status_code == 200 and "video/mp4" in r.headers.get("content-type", ""):
            return cam_id, url
    except Exception:
        pass
    return None

def harvest_niteroi():
    print("[Niterói] Varrendo IDs de câmeras (000001 a 000100)...")
    
    # Varre uma faixa de IDs (ajuste se necessário)
    ids = [f"{i:06d}" for i in range(1, 101)]
    
    cameras = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        resultados = list(executor.map(testar_id, ids))
        
        for res in resultados:
            if res:
                cam_id, stream_url = res
                cameras.append({
                    "slug": f"niteroi-{cam_id}",
                    "nome": f"Câmera Niterói {cam_id}",
                    "cidade": "Niterói",
                    "bairro": "Niterói",
                    "regiao": "Rio de Janeiro",
                    "pais": "Brasil",
                    "codigo_pais": "BR",
                    "latitude": -22.8832,  # Centro de Niterói (ajuste depois)
                    "longitude": -43.1034,
                    "categoria": "Transito",
                    "fonte": "NitTrans",
                    "pagina_oficial": "https://appnittrans.niteroi.rj.gov.br/",
                    "stream_url": stream_url,
                    "tipo_stream": "video",
                    "autorizada": True,
                    "pode_retransmitir": True,
                    "online": True,
                    "origem": "niteroi",
                    "origem_id": cam_id,
                    "video_id": None,
                })

    print(f"  -> {len(cameras)} câmeras encontradas.")
    return cameras

if __name__ == "__main__":
    cams = harvest_niteroi()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} | {c['stream_url']}")
        
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
