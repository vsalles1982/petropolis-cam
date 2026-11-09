#!/usr/bin/env python3
import re
import sys
import httpx
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

BASE_URL = "https://opencctv.org"
# Bairros principais de NYC (e variações de nome)
BAIRROS = ["manhattan", "brooklyn", "queens", "bronx", "staten-island", "new-york-city", "new-york"]

def harvest_nyc_bairros():
    print("[NYC Full] Buscando câmeras por bairro...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    cameras = []
    for bairro in BAIRROS:
        print(f"  -> Buscando em {bairro}...")
        # Tenta acessar a página do bairro
        url_bairro = f"{BASE_URL}/sv/cameras/united-states/new-york/{bairro}"
        try:
            r = httpx.get(url_bairro, headers=headers, timeout=30, follow_redirects=True)
            if r.status_code != 200:
                continue
            
            # Extrai os links das câmeras dentro desse bairro
            links_cam = re.findall(rf'/sv/cameras/united-states/new-york/{bairro}/[a-zA-Z0-9\-]+', r.text)
            
            for link in set(links_cam):
                try:
                    url_cam = f"{BASE_URL}{link}"
                    r_cam = httpx.get(url_cam, headers=headers, timeout=15, follow_redirects=True)
                    
                    # Extrai o link .m3u8 (vídeo HLS)
                    m3u8_match = re.search(r'(https?://[^"\']+\.m3u8)', r_cam.text)
                    if not m3u8_match:
                        continue
                    
                    lat_match = re.search(r'"lat(?:itude)?":\s*([\-0-9\.]+)', r_cam.text)
                    lon_match = re.search(r'"lo(?:n|ngitude)":\s*([\-0-9\.]+)', r_cam.text)
                    nome_match = re.search(r'<title>(.*?)</title>', r_cam.text)
                    
                    lat = float(lat_match.group(1)) if lat_match else 0.0
                    lon = float(lon_match.group(1)) if lon_match else 0.0
                    nome = nome_match.group(1).replace(" | OpenCCTV", "").strip() if nome_match else link.split('/')[-1].replace('-', ' ').title()
                    cam_id = link.split('/')[-1]
                    
                    cameras.append({
                        "slug": f"nycdot-{cam_id}",
                        "nome": nome,
                        "cidade": bairro.replace("-", " ").title(),
                        "bairro": "New York",
                        "regiao": "New York",
                        "pais": "Estados Unidos",
                        "codigo_pais": "US",
                        "latitude": lat,
                        "longitude": lon,
                        "categoria": "Transito",
                        "fonte": "NY DOT",
                        "pagina_oficial": url_cam,
                        "stream_url": m3u8_match.group(1),
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
        except Exception:
            pass

    print(f"  -> {len(cameras)} câmeras encontradas nos bairros de NYC.")
    return cameras

if __name__ == "__main__":
    cams = harvest_nyc_bairros()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} ({c['cidade']}) | {c['stream_url']}")
        
        print("\nGravando no banco de dados...")
        gravar(cams)
