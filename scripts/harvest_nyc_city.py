#!/usr/bin/env python3
import sys
import httpx
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def harvest_nyc_city():
    print("[NYC City] Buscando câmeras oficiais do NYC DOT...")
    url_api = "https://webcams.nyctmc.org/api/cameras"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        r = httpx.get(url_api, headers=headers, timeout=30, follow_redirects=True)
        r.raise_for_status()
        dados = r.json()
    except Exception as e:
        print(f"  !! Erro: {e}")
        return []

    print(f"  -> {len(dados)} câmeras brutas encontradas na API.")
    
    cameras = []
    for c in dados:
        try:
            # A API retorna os campos: id, name, latitude, longitude, imageUrl, etc.
            cam_id = str(c.get("id"))
            image_url = c.get("imageUrl")
            
            if not image_url:
                continue
                
            cameras.append({
                "slug": f"nyctmc-{cam_id}",
                "nome": c.get("name", "NYC Camera"),
                "cidade": "New York",
                "bairro": c.get("area", "NYC"),
                "regiao": "New York",
                "pais": "Estados Unidos",
                "codigo_pais": "US",
                "latitude": float(c.get("latitude", 0)),
                "longitude": float(c.get("longitude", 0)),
                "categoria": "Transito",
                "fonte": "NYC DOT",
                "pagina_oficial": "https://webcams.nyctmc.org/",
                "stream_url": image_url,
                "tipo_stream": "imagem", # O player já sabe atualizar isso
                "autorizada": True,
                "pode_retransmitir": True,
                "online": c.get("isOnline", True),
                "origem": "nyctmc",
                "origem_id": cam_id,
                "video_id": None,
            })
        except Exception:
            pass

    print(f"  -> {len(cameras)} câmeras normalizadas.")
    return cameras

if __name__ == "__main__":
    cams = harvest_nyc_city()
    if cams:
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
