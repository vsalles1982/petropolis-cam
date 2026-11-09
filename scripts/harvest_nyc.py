#!/usr/bin/env python3
import re
import sys
import httpx
from pathlib import Path

# Adiciona o diretório do projeto ao path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

BASE_URL = "https://opencctv.org"
NY_URL = f"{BASE_URL}/sv/cameras/united-states/new-york"

def harvest_nyc():
    print("[NYC] Buscando cidades e câmeras...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    cameras = []
    try:
        # 1. Pega a página principal de NY para achar as cidades/bairros
        r = httpx.get(NY_URL, headers=headers, timeout=30, follow_redirects=True)
        r.raise_for_status()
        
        # Acha todos os links de cidades
        cidades = set(re.findall(r'/sv/cameras/united-states/new-york/([a-z\-]+)(?="|/)', r.text))
        
        # Filtra para ignorar categorias que não são cidades
        cidades = [c for c in cidades if c not in ["category", "airport", "beach", "nature", "ski", "traffic", "weather"]]
        print(f"  -> {len(cidades)} cidades/bairros encontrados.")
        
        for cidade in cidades:
            print(f"  -> Buscando em {cidade}...")
            url_cidade = f"{NY_URL}/{cidade}"
            r_cidade = httpx.get(url_cidade, headers=headers, timeout=30, follow_redirects=True)
            
            # Acha os links das câmeras específicas
            cameras_links = re.findall(rf'/sv/cameras/united-states/new-york/{cidade}/[a-zA-Z0-9\-]+', r_cidade.text)
            
            for link in set(cameras_links):
                url_cam = f"{BASE_URL}{link}"
                try:
                    r_cam = httpx.get(url_cam, headers=headers, timeout=15, follow_redirects=True)
                    
                    # Extrai o link .m3u8
                    m3u8_match = re.search(r'(https?://[^"\']+\.m3u8)', r_cam.text)
                    if not m3u8_match:
                        continue
                    stream_url = m3u8_match.group(1)
                    
                    # Extrai lat/lon
                    lat_match = re.search(r'"lat(?:itude)?":\s*([\-0-9\.]+)', r_cam.text)
                    lon_match = re.search(r'"lo(?:n|ngitude)":\s*([\-0-9\.]+)', r_cam.text)
                    
                    lat = float(lat_match.group(1)) if lat_match else 0.0
                    lon = float(lon_match.group(1)) if lon_match else 0.0
                    
                    # Tenta extrair o nome da câmera
                    nome_match = re.search(r'<title>(.*?)</title>', r_cam.text)
                    nome = nome_match.group(1).replace(" | OpenCCTV", "").strip() if nome_match else link.split('/')[-1].replace('-', ' ').title()
                    
                    cam_id = link.split('/')[-1]
                    
                    cameras.append({
                        "slug": f"nycdot-{cam_id}",
                        "nome": nome,
                        "cidade": cidade.replace("-", " ").title(),
                        "bairro": "New York",
                        "regiao": "New York",
                        "pais": "Estados Unidos",
                        "codigo_pais": "US",
                        "latitude": lat,
                        "longitude": lon,
                        "categoria": "Transito",
                        "fonte": "NY DOT",
                        "pagina_oficial": url_cam,
                        "stream_url": stream_url,
                        "tipo_stream": "hls",
                        "autorizada": True,
                        "pode_retransmitir": True,
                        "online": True,
                        "origem": "nycdot",
                        "origem_id": cam_id,
                        "video_id": None,
                    })
                except Exception:
                    pass 
                    
    except Exception as e:
        print(f"  !! Erro: {e}")
        return []

    print(f"  -> {len(cameras)} câmeras encontradas e normalizadas.")
    return cameras

if __name__ == "__main__":
    cams = harvest_nyc()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} ({c['cidade']}) | {c['stream_url']}")
        
        print("\nGravando no banco de dados...")
        gravar(cams)
