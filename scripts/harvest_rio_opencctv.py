#!/usr/bin/env python3
import sys
import re
import httpx
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

# O padrão de URL do OpenCCTV para o Rio é bem flexível no slug.
# A gente vai usar um placeholder e testar o ID.
URL_BASE = "https://opencctv.org/cameras/brazil/rj/rio-de-janeiro/camera-{id}"

def testar_camera(cam_id: int):
    url = URL_BASE.format(id=cam_id)
    try:
        # Usamos um timeout curto para ser rápido
        r = httpx.get(url, timeout=8, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "Rio de Janeiro" in r.text:
            # Extrai as coordenadas do texto (formato: -22.xxxx, -43.xxxx)
            coord_match = re.search(r'(-2[0-9]\.\d+)\s*,\s*(-4[0-9]\.\d+)', r.text)
            if coord_match:
                lat = float(coord_match.group(1))
                lon = float(coord_match.group(2))
                
                # Tenta extrair o nome do título
                nome_match = re.search(r'<h1[^>]*>(.*?)</h1>', r.text, re.DOTALL)
                nome = re.sub(r'<[^>]+>', '', nome_match.group(1)).strip() if nome_match else f"Câmera Rio {cam_id}"
                
                # Tenta extrair o link do feed MJPEG
                feed_match = re.search(r'(https?://[^"\']+\.(?:mjpg|mjpeg|jpg)[^"\']*)', r.text, re.IGNORECASE)
                feed_url = feed_match.group(1) if feed_match else None
                
                if feed_url:
                    return cam_id, url, nome, lat, lon, feed_url
    except Exception:
        pass
    return None

def harvest_rio():
    print("[Rio] Varrendo IDs do OpenCCTV (faixas amplas)...")
    
    # Faixas baseadas nos exemplos reais encontrados na busca
    ids_para_testar = []
    ids_para_testar.extend(range(288000, 288200)) # Ex: 288138
    ids_para_testar.extend(range(341200, 341400)) # Ex: 341321
    ids_para_testar.extend(range(365500, 365700)) # Ex: 365593
    ids_para_testar.extend(range(397800, 398000)) # Ex: 397899
    
    # Adiciona mais algumas faixas para garantir
    ids_para_testar.extend(range(340000, 342000))
    
    cameras = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        resultados = list(executor.map(testar_camera, ids_para_testar))
        
        for res in resultados:
            if res:
                cam_id, url, nome, lat, lon, feed_url = res
                cameras.append({
                    "slug": f"rio-{cam_id}",
                    "nome": nome,
                    "cidade": "Rio de Janeiro",
                    "bairro": "Rio de Janeiro",
                    "regiao": "Rio de Janeiro",
                    "pais": "Brasil",
                    "codigo_pais": "BR",
                    "latitude": lat,
                    "longitude": lon,
                    "categoria": "Transito",
                    "fonte": "OpenCCTV (Rio)",
                    "pagina_oficial": url,
                    "stream_url": feed_url,
                    "tipo_stream": "imagem", # MJPEG funciona como imagem no player
                    "autorizada": True,
                    "pode_retransmitir": True,
                    "online": True,
                    "origem": "rio_opencctv",
                    "origem_id": str(cam_id),
                    "video_id": None,
                })
                print(f"  ✅ Encontrada: {nome} (ID: {cam_id})")

    print(f"  -> {len(cameras)} câmeras do Rio encontradas.")
    return cameras

if __name__ == "__main__":
    cams = harvest_rio()
    if cams:
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
