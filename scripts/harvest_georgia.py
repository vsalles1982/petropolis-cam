#!/usr/bin/env python3
import sys
import httpx
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def harvest_georgia():
    print("[Georgia] Buscando câmeras via ArcGIS (GDOT)...")
    # Endpoint ArcGIS do GDOT
    url_api = "https://services1.arcgis.com/2iUE8l8JKrP2tygQ/ArcGIS/rest/services/GDOT_511_Cameras/FeatureServer/0/query?where=1%3D1&outFields=*&f=json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    try:
        r = httpx.get(url_api, headers=headers, timeout=30, follow_redirects=True)
        r.raise_for_status()
        dados = r.json()
    except Exception as e:
        print(f"  !! Erro ao acessar a API: {e}")
        return []

    features = dados.get("features", [])
    print(f"  -> {len(features)} câmeras brutas encontradas no ArcGIS.")

    cameras = []
    for feat in features:
        attr = feat.get("attributes", {})
        try:
            # Pula as câmeras desativadas
            if attr.get("Status") == "Disabled":
                continue

            # Extrai os dados
            cam_id = str(attr.get("Id"))
            lat = attr.get("Latitude")
            lon = attr.get("Longitude")
            stream_url = attr.get("VideoUrl")
            
            # Pula se não tiver link de vídeo ou se as coordenadas forem 0,0
            if not stream_url or ".m3u8" not in str(stream_url):
                continue
            if not lat or not lon or (float(lat) == 0.0 and float(lon) == 0.0):
                continue

            cameras.append({
                "slug": f"georgia-{cam_id}",
                "nome": attr.get("Description") or f"GDOT Camera {cam_id}",
                "cidade": "Georgia",
                "bairro": attr.get("Roadway") or "Georgia",
                "regiao": "Georgia",
                "pais": "Estados Unidos",
                "codigo_pais": "US",
                "latitude": float(lat),
                "longitude": float(lon),
                "categoria": "Transito",
                "fonte": "GDOT 511",
                "pagina_oficial": attr.get("Url"),
                "stream_url": stream_url,
                "tipo_stream": "hls",
                "autorizada": True,
                "pode_retransmitir": True,
                "online": True,
                "origem": "georgia_gdot",
                "origem_id": cam_id,
                "video_id": None,
            })
        except Exception as e:
            continue

    print(f"  -> {len(cameras)} câmeras ativas com link HLS e coordenadas válidas.")
    return cameras

if __name__ == "__main__":
    cams = harvest_georgia()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} | {c['stream_url']}")
        
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
