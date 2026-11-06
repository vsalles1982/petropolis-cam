#!/usr/bin/env python3
import sys
from pathlib import Path

# Adiciona o diretório do projeto ao path para importar o backend
sys.path.append(str(Path(__file__).resolve().parent.parent))

from scripts.harvest_world import gravar
import httpx

def harvest_tfl():
    print("[TfL] Buscando câmeras de Londres...")
    url = "https://api.tfl.gov.uk/Place/Type/JamCam"
    try:
        r = httpx.get(url, timeout=60)
        r.raise_for_status()
        lugares = r.json()
    except Exception as e:
        print(f"  !! Erro ao acessar API: {e}")
        return []

    print(f"  -> {len(lugares)} câmeras brutas na API")
    
    cameras = []
    for lugar in lugares:
        props = {p['key']: p['value'] for p in lugar.get('additionalProperties', []) if 'key' in p}
        
        if props.get('available', '').lower() != 'true':
            continue
            
        stream_url = props.get('videoUrl') or props.get('imageUrl')
        if not stream_url:
            continue
            
        tipo = "video" if props.get('videoUrl') else "imagem"
        raw_id = lugar.get('id', '').replace('JamCams_', '')
        
        cameras.append({
            "slug": f"tfl-{raw_id}",
            "nome": lugar.get('commonName', 'TfL Camera'),
            "cidade": "London",
            "bairro": "London",
            "regiao": "England",
            "pais": "Reino Unido",
            "codigo_pais": "GB",
            "latitude": float(lugar.get('lat', 0)),
            "longitude": float(lugar.get('lon', 0)),
            "categoria": "Transito",
            "fonte": "TfL",
            "pagina_oficial": "https://tfl.gov.uk/traffic/status/",
            "stream_url": stream_url,
            "tipo_stream": tipo,
            "autorizada": True,
            "pode_retransmitir": False,
            "online": True,
            "origem": "tfl",
            "origem_id": raw_id,
            "video_id": None,
        })
    
    print(f"  -> {len(cameras)} câmeras normalizadas e prontas")
    return cameras

if __name__ == "__main__":
    cams = harvest_tfl()
    if cams:
        print(f"\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} | {c['stream_url']}")
        print("\nGravando no banco de dados...")
        gravar(cams)
