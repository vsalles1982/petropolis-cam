#!/usr/bin/env python3
import sys
import httpx
import json
import re
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def extrair_coordenadas(c):
    try:
        wkt = c.get("latLng", {}).get("geography", {}).get("wellKnownText", "")
        match = re.search(r'POINT\s*\(\s*([-0-9.]+)\s+([-0-9.]+)\s*\)', wkt)
        if match:
            return float(match.group(2)), float(match.group(1)) # lat, lon
    except Exception:
        pass
    return None, None

def harvest_estado(nome, url_base, origem, pais, codigo_pais):
    print(f"[{nome}] Buscando câmeras...")
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
        payload = {"draw": 1, "start": start, "length": length, "columns": [], "order": [], "search": {"value": "", "regex": False}}
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
                lat, lon = extrair_coordenadas(c)
                if not lat or not lon: continue
                images = c.get("images", [])
                if not images: continue
                img = images[0]
                video_url = img.get("videoUrl")
                image_url = img.get("imageUrl")
                if video_url and ".m3u8" in video_url:
                    stream_url = video_url
                    tipo = "hls"
                elif image_url:
                    stream_url = f"https://{url_base}{image_url}" if image_url.startswith("/") else image_url
                    tipo = "imagem"
                else: continue
                cameras.append({
                    "slug": f"{origem}-{c.get('id')}", "nome": img.get("description") or c.get("roadway") or f"Camera {c.get('id')}",
                    "cidade": c.get("county") or c.get("city") or nome, "bairro": c.get("roadway") or nome,
                    "regiao": nome, "pais": pais, "codigo_pais": codigo_pais,
                    "latitude": lat, "longitude": lon, "categoria": "Transito",
                    "fonte": f"{nome} 511", "pagina_oficial": f"https://{url_base}/map/Cctv/{c.get('id')}",
                    "stream_url": stream_url, "tipo_stream": tipo, "autorizada": True,
                    "pode_retransmitir": True, "online": True, "origem": origem,
                    "origem_id": str(c.get("id")), "video_id": None,
                })
            except Exception: continue
        print(f"  -> Página {start//length + 1}: +{len(registros)} (total: {len(cameras)})")
        if len(registros) < length: break
        start += length
    print(f"  -> {len(cameras)} câmeras de {nome}.")
    return cameras

if __name__ == "__main__":
    # Lista de estados Travel-IQ (adicione/remova conforme necessário)
    estados = [
        ("Nova York", "511ny.org", "ny511", "Estados Unidos", "US"),
        ("Nevada", "nvroads.com", "nv511", "Estados Unidos", "US"),
        ("Louisiana", "511la.org", "la511", "Estados Unidos", "US"),
        ("Wisconsin", "511wi.gov", "wi511", "Estados Unidos", "US"),
        ("Carolina do Norte", "drivenc.gov", "nc511", "Estados Unidos", "US"),
        ("Utah", "udottraffic.utah.gov", "ut511", "Estados Unidos", "US"),
        ("Arizona", "az511.com", "az511", "Estados Unidos", "US"),
        ("New England", "newengland511.org", "ne511", "Estados Unidos", "US"),
        ("Alberta", "511.alberta.ca", "ab511", "Canadá", "CA"),
    ]
    todos = []
    for nome, url, origem, pais, cod in estados:
        todos.extend(harvest_estado(nome, url, origem, pais, cod))
    if todos:
        print(f"\nGravando {len(todos)} câmeras no banco...")
        gravar(todos)
