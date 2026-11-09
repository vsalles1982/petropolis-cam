#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

PROXY_BASE = "https://nycguessr.vercel.app"

def harvest_nyc_fotos():
    print("[NYC Fotos] Lendo câmeras do arquivo extraído...")
    
    arquivo = Path("/tmp/nyc_cams_clean.json")
    if not arquivo.exists():
        print(f"  !! Arquivo não encontrado: {arquivo}")
        return []
    
    with arquivo.open() as f:
        dados = json.load(f)
    
    print(f"  -> {len(dados)} câmeras brutas.")
    
    cameras = []
    for c in dados:
        try:
            # Extrai o ID da URL original: .../cameras/{id}/image
            u_original = c.get("u", "")
            if not u_original:
                continue
            
            # Pega o pedaço entre "cameras/" e "/image"
            partes = u_original.split("/")
            try:
                idx = partes.index("cameras")
                cam_id = partes[idx + 1]
            except (ValueError, IndexError):
                continue
            
            nome = c.get("n") or "NYC Camera"
            lat = c.get("lat") or 0
            lng = c.get("lng") or 0
            area = c.get("a") or "NYC"
            
            # URL da imagem passando pelo proxy do NYCGuessr (que está nos EUA)
            image_url = f"{PROXY_BASE}/api/cam/{cam_id}"
            
            cameras.append({
                "slug": f"nyctmc-{cam_id}",
                "nome": nome,
                "cidade": "New York",
                "bairro": area,
                "regiao": "New York",
                "pais": "Estados Unidos",
                "codigo_pais": "US",
                "latitude": float(lat),
                "longitude": float(lng),
                "categoria": "Transito",
                "fonte": "NYC DOT (via NYCGuessr)",
                "pagina_oficial": "https://webcams.nyctmc.org/",
                "stream_url": image_url,
                "tipo_stream": "imagem",
                "autorizada": True,
                "pode_retransmitir": True,
                "online": True,
                "origem": "nyctmc_proxy",
                "origem_id": cam_id,
                "video_id": None,
            })
        except Exception as e:
            print(f"  !! Erro em uma câmera: {e}")
            continue
    
    print(f"  -> {len(cameras)} câmeras normalizadas.")
    return cameras

if __name__ == "__main__":
    cams = harvest_nyc_fotos()
    if cams:
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
