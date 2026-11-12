#!/usr/bin/env python3
import sys
import httpx
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def harvest_madrid():
    print("[Madrid] Buscando câmeras da M-30 via XML Oficial...")
    url_xml = "https://datos.madrid.es/egob/catalogo/212166-7899870-trafico-calle30-camaras.xml"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        r = httpx.get(url_xml, headers=headers, timeout=30, follow_redirects=True)
        r.raise_for_status()
        xml_data = r.content
    except Exception as e:
        print(f"  !! Erro ao acessar o XML: {e}")
        return []

    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"  !! Erro ao fazer parse do XML: {e}")
        return []

    cameras = []
    
    # Itera sobre as tags <Camara>
    for cam in root.findall("Camara"):
        try:
            lat = float(cam.find("Posicion/Latitud").text)
            lon = float(cam.find("Posicion/Longitud").text)
            nome = cam.find("Nombre").text
            url_original = cam.find("URL").text
            
            if not url_original:
                continue

            # Garante que a URL tenha o protocolo https
            if not url_original.startswith("http"):
                url_img = f"https://{url_original}"
            else:
                url_img = url_original

            # Passa a imagem pelo proxy para driblar CORS/Referer
            proxy_url = f"/api/proxy?url={url_img}"

            cameras.append({
                "slug": f"madrid-{nome}",
                "nome": f"M-30 - {nome}",
                "cidade": "Madrid",
                "bairro": "M-30",
                "regiao": "Comunidad de Madrid",
                "pais": "Espanha",
                "codigo_pais": "ES",
                "latitude": lat,
                "longitude": lon,
                "categoria": "Transito",
                "fonte": "Ayuntamiento de Madrid",
                "pagina_oficial": "https://datos.madrid.es/",
                "stream_url": proxy_url,
                "tipo_stream": "imagem", # Plano B (Dourado 🏆)
                "autorizada": True,
                "pode_retransmitir": True,
                "online": True,
                "origem": "madrid_m30",
                "origem_id": nome,
                "video_id": None,
            })
        except Exception as e:
            print(f"  !! Erro em uma câmera: {e}")
            continue

    print(f"  -> {len(cameras)} câmeras encontradas na M-30.")
    return cameras

if __name__ == "__main__":
    cams = harvest_madrid()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} | {c['stream_url']}")
        
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
