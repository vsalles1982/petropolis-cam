#!/usr/bin/env python3
import sys
import httpx
import json
import re
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def extrair_coordenadas(c):
    """Extrai lat/lon do campo WKT (wellKnownText)"""
    try:
        # O formato é "POINT (-80.892882 26.17325)" -> lon, lat
        wkt = c.get("latLng", {}).get("geography", {}).get("wellKnownText", "")
        match = re.search(r'POINT\s*\(\s*([-0-9.]+)\s+([-0-9.]+)\s*\)', wkt)
        if match:
            lon = float(match.group(1))
            lat = float(match.group(2))
            return lat, lon
    except Exception:
        pass
    return None, None

def harvest_estado(nome, url_base, origem, pais, codigo_pais):
    print(f"[{nome}] Buscando câmeras via POST paginado...")
    
    url_api = f"https://{url_base}/List/GetData/Cameras"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://{url_base}/",
        "Content-Type": "application/json"
    }
    
    cameras = []
    start = 0
    length = 100
    
    while True:
        payload = {
            "draw": 1,
            "start": start,
            "length": length,
            "columns": [],
            "order": [],
            "search": {"value": "", "regex": False}
        }
        
        try:
            r = httpx.post(url_api, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            dados = r.json()
        except Exception as e:
            print(f"  !! Erro na página {start}: {e}")
            break
            
        registros = dados.get("data", [])
        if not registros:
            break
            
        for c in registros:
            try:
                # Extrai coordenadas
                lat, lon = extrair_coordenadas(c)
                if not lat or not lon:
                    continue

                # Extrai a mídia
                images = c.get("images", [])
                if not images:
                    continue
                
                img = images[0]
                video_url = img.get("videoUrl")
                image_url = img.get("imageUrl")
                
                if video_url and ".m3u8" in video_url:
                    stream_url = video_url
                    tipo = "hls"
                elif image_url:
                    if image_url.startswith("/"):
                        stream_url = f"https://{url_base}{image_url}"
                    else:
                        stream_url = image_url
                    tipo = "imagem"
                else:
                    continue
                    
                cameras.append({
                    "slug": f"{origem}-{c.get('id')}",
                    "nome": img.get("description") or c.get("roadway") or f"Camera {c.get('id')}",
                    "cidade": c.get("county") or c.get("city") or nome,
                    "bairro": c.get("roadway") or nome,
                    "regiao": nome,
                    "pais": pais,
                    "codigo_pais": codigo_pais,
                    "latitude": lat,
                    "longitude": lon,
                    "categoria": "Transito",
                    "fonte": f"{nome} 511",
                    "pagina_oficial": f"https://{url_base}/map/Cctv/{c.get('id')}",
                    "stream_url": stream_url,
                    "tipo_stream": tipo,
                    "autorizada": True,
                    "pode_retransmitir": True,
                    "online": True,
                    "origem": origem,
                    "origem_id": str(c.get("id")),
                    "video_id": None,
                })
            except Exception:
                continue
                
        print(f"  -> Página {start//length + 1}: +{len(registros)} registros (total acumulado: {len(cameras)})")
        
        if len(registros) < length:
            break
            
        start += length

    print(f"  -> {len(cameras)} câmeras extraídas de {nome}.")
    return cameras

if __name__ == "__main__":
    todos = []
    todos.extend(harvest_estado("Flórida", "fl511.com", "fl511", "Estados Unidos", "US"))
    todos.extend(harvest_estado("Ontário", "511on.ca", "on511", "Canadá", "CA"))
    
    if todos:
        print(f"\nGravando {len(todos)} câmeras no banco...")
        gravar(todos)
