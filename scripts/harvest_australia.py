#!/usr/bin/env python3
import sys
import httpx
import json
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def harvest_nsw():
    print("[NSW] Buscando câmeras via GeoJSON...")
    url = "https://data.livetraffic.com/cameras/traffic-cam.json"
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        dados = r.json()
    except Exception as e:
        print(f"  !! Erro: {e}")
        return []
    
    features = dados.get("features", [])
    print(f"  -> {len(features)} câmeras brutas.")
    cameras = []
    for feat in features:
        try:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if len(coords) < 2: continue
            lon, lat = coords[0], coords[1]
            href = props.get("href")
            if not href: continue
            cameras.append({
                "slug": f"nsw-{props.get('title', 'cam')}", "nome": props.get("title") or "NSW Camera",
                "cidade": props.get("region") or "NSW", "bairro": props.get("view") or "NSW",
                "regiao": "New South Wales", "pais": "Austrália", "codigo_pais": "AU",
                "latitude": float(lat), "longitude": float(lon), "categoria": "Transito",
                "fonte": "Live Traffic NSW", "pagina_oficial": "https://livetraffic.com/",
                "stream_url": href, "tipo_stream": "imagem", "autorizada": True,
                "pode_retransmitir": True, "online": True, "origem": "nsw_livetraffic",
                "origem_id": props.get("title", str(lat)+str(lon)), "video_id": None,
            })
        except Exception: continue
    print(f"  -> {len(cameras)} câmeras NSW.")
    return cameras

def harvest_qld():
    print("[QLD] Buscando câmeras via GeoJSON (API Key pública)...")
    # A chave pública do QLDTraffic
    url = "https://api.qldtraffic.qld.gov.au/v1/webcams?apikey=3e83add325cbb69ac4d8e5bf433d770b"
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        dados = r.json()
    except Exception as e:
        print(f"  !! Erro: {e}")
        return []
    
    features = dados.get("features", [])
    print(f"  -> {len(features)} câmeras brutas.")
    cameras = []
    for feat in features:
        try:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [])
            if len(coords) < 2: continue
            lon, lat = coords[0], coords[1]
            image_url = props.get("image_url")
            if not image_url: continue
            cameras.append({
                "slug": f"qld-{props.get('id')}", "nome": props.get("description") or "QLD Camera",
                "cidade": props.get("locality") or "Queensland", "bairro": props.get("district") or "QLD",
                "regiao": "Queensland", "pais": "Austrália", "codigo_pais": "AU",
                "latitude": float(lat), "longitude": float(lon), "categoria": "Transito",
                "fonte": "QLDTraffic", "pagina_oficial": "https://qldtraffic.qld.gov.au/",
                "stream_url": image_url, "tipo_stream": "imagem", "autorizada": True,
                "pode_retransmitir": True, "online": True, "origem": "qld_traffic",
                "origem_id": str(props.get("id")), "video_id": None,
            })
        except Exception: continue
    print(f"  -> {len(cameras)} câmeras QLD.")
    return cameras

if __name__ == "__main__":
    todos = []
    todos.extend(harvest_nsw())
    todos.extend(harvest_qld())
    if todos:
        print(f"\nGravando {len(todos)} câmeras no banco...")
        gravar(todos)
