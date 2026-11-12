#!/usr/bin/env python3
import sys
import httpx
import json
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def harvest_caltrans():
    print("[Caltrans] Buscando câmeras em todos os distritos da Califórnia...")
    
    cameras = []
    # Loop do Distrito 1 ao 12
    for distrito in range(1, 13):
        url = f"https://cwwp2.dot.ca.gov/data/d{distrito}/cctv/cctvStatusD{distrito:02d}.json"
        print(f"  -> Buscando Distrito {distrito}...")
        
        try:
            r = httpx.get(url, timeout=30, follow_redirects=True)
            r.raise_for_status()
            dados = r.json()
        except Exception as e:
            print(f"     !! Erro no Distrito {distrito}: {e}")
            continue

        # A estrutura é {"data": [{"cctv": {...}}]}
        for item in dados.get("data", []):
            cctv = item.get("cctv", {})
            location = cctv.get("location", {})
            image_data = cctv.get("imageData", {})
            
            # Filtra apenas câmeras em serviço e com vídeo HLS
            if not cctv.get("inService") or cctv.get("inService") == "false":
                continue
            
            stream_url = image_data.get("streamingVideoURL")
            if not stream_url or stream_url == "Not Reported":
                continue

            # Extrai dados
            lat = location.get("latitude")
            lon = location.get("longitude")
            nome = location.get("locationName", "Caltrans Camera")
            route = location.get("route", "")
            county = location.get("county", "California")
            
            if not lat or not lon:
                continue

            cameras.append({
                "slug": f"caltrans-d{distrito}-{cctv.get('index')}",
                "nome": f"{route} - {nome}",
                "cidade": county,
                "bairro": route,
                "regiao": f"Distrito {distrito}",
                "pais": "Estados Unidos",
                "codigo_pais": "US",
                "latitude": float(lat),
                "longitude": float(lon),
                "categoria": "Transito",
                "fonte": "Caltrans",
                "pagina_oficial": "https://cwwp2.dot.ca.gov/",
                "stream_url": stream_url,
                "tipo_stream": "hls",
                "autorizada": True,
                "pode_retransmitir": True,
                "online": True,
                "origem": "caltrans",
                "origem_id": str(cctv.get("index")),
                "video_id": None,
            })

    print(f"  -> {len(cameras)} câmeras com vídeo HLS encontradas na Califórnia.")
    return cameras

if __name__ == "__main__":
    cams = harvest_caltrans()
    if cams:
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
