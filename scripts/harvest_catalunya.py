#!/usr/bin/env python3
import sys
import httpx
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from scripts.harvest_world import gravar

def harvest_catalunya():
    print("[Catalunya] Buscando câmeras via XML Oficial (SCT)...")
    url_xml = "http://www.gencat.cat/transit/opendata/cameres.xml"
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

    # Vias alvo em Barcelona e arredores
    vias_alvo = ["B-10", "B-20", "B-23", "C-31", "C-32", "C-58", "A-2"]
    
    cameras = []
    
    # Acha todas as tags "cameres" (ignorando o namespace)
    for elem in root.iter():
        if elem.tag.endswith('cameres'):
            # Pega os dados das tags filhas
            dados = {}
            for child in elem:
                tag_nome = child.tag.split('}')[-1] # Remove o namespace
                dados[tag_nome] = child.text
            
            via = dados.get("carretera", "")
            
            # Filtra pelas vias alvo
            if not any(alvo in via.upper() for alvo in vias_alvo):
                continue

            # Extrai as coordenadas de dentro da tag <geom>
            # O formato geralmente é <gml:Point><gml:coordinates>lat,lon</gml:coordinates></gml:Point>
            lat = None
            lon = None
            geom = elem.find("{http://www.opengeospatial.net/cite}geom")
            if geom is not None:
                # Procura a tag de coordenadas em qualquer sub-nível do geom
                for sub in geom.iter():
                    if sub.tag.endswith('coordinates') or sub.tag.endswith('pos'):
                        if sub.text:
                            coords = sub.text.strip().split(',')
                            if len(coords) >= 2:
                                # Dependendo do WFS, pode vir "lat, lon" ou "lon, lat"
                                # Vamos assumir lat, lon conforme padrão GML
                                try:
                                    lat = float(coords[0].strip())
                                    lon = float(coords[1].strip())
                                except ValueError:
                                    pass
                            break
            
            url_img = dados.get("link")
            municipi = dados.get("municipi", "Barcelona")
            pk = dados.get("pk", "")

            if not lat or not lon or not url_img:
                continue

            # Cria um ID único baseado na via, municipio e pk
            cam_id = f"{via}-{municipi}-{pk}".replace(" ", "").replace("/", "")

            cameras.append({
                "slug": f"cat-{cam_id}",
                "nome": f"{via} - {municipi} (PK {pk})",
                "cidade": municipi.title(),
                "bairro": via,
                "regiao": "Catalunya",
                "pais": "Espanha",
                "codigo_pais": "ES",
                "latitude": lat,
                "longitude": lon,
                "categoria": "Transito",
                "fonte": "SCT Catalunya",
                "pagina_oficial": "http://www.gencat.cat/transit/",
                "stream_url": url_img,
                "tipo_stream": "imagem", # Plano B (Dourado 🏆)
                "autorizada": True,
                "pode_retransmitir": True,
                "online": True,
                "origem": "sct_catalunya",
                "origem_id": cam_id,
                "video_id": None,
            })

    print(f"  -> {len(cameras)} câmeras encontradas nas vias de Barcelona.")
    return cameras

if __name__ == "__main__":
    cams = harvest_catalunya()
    if cams:
        print("\nAmostra:")
        for c in cams[:3]:
            print(f"  - {c['nome']} | {c['stream_url']}")
        
        print(f"\nGravando {len(cams)} câmeras no banco...")
        gravar(cams)
