#!/usr/bin/env python3
import sys
import httpx
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

BASE_URL = "http://200.144.30.103:8084"

def testar_camera(cam_id: int):
    """Testa se a câmera existe e responde com um stream válido."""
    stream_url = f"{BASE_URL}/hls/cam_{cam_id}/stream.m3u8"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": f"{BASE_URL}/"
    }
    try:
        r = httpx.get(stream_url, headers=headers, timeout=5)
        if r.status_code == 200 and "mpegurl" in r.headers.get("content-type", ""):
            return cam_id, stream_url
    except Exception:
        pass
    return None

def harvest_der_sp():
    print("[DER-SP] Varrendo IDs de câmeras (1 a 100)...")
    
    cameras = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        resultados = list(executor.map(testar_camera, range(1, 101)))
        
        for res in resultados:
            if res:
                cam_id, stream_url = res
                cameras.append({
                    "slug": f"dersp-{cam_id}",
                    "nome": f"Câmera DER-SP {cam_id}",
                    "cidade": "São Paulo",
                    "bairro": "Rodovias DER-SP",
                    "regiao": "São Paulo",
                    "pais": "Brasil",
                    "codigo_pais": "BR",
                    "latitude": -23.5505,  # Coordenada aproximada (centro de SP)
                    "longitude": -46.6333,
                    "categoria": "Transito",
                    "fonte": "DER-SP",
                    "pagina_oficial": "http://200.144.30.103:8084/",
                    "stream_url": stream_url,
                    "tipo_stream": "hls",
                    "autorizada": True,
                    "pode_retransmitir": True,
                    "online": True,
                    "origem": "der_sp",
                    "origem_id": str(cam_id),
                    "video_id": None,
                })

    print(f"  -> {len(cameras)} câmeras encontradas no DER-SP.")
    return cameras

if __name__ == "__main__":
    cams = harvest_der_sp()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} | {c['stream_url']}")
        
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
