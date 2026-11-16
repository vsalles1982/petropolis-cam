#!/usr/bin/env python3
import sqlite3
import httpx
import asyncio
import sys
from pathlib import Path
import shutil

DB_PATH = Path("data/cameras.db")
BACKUP_PATH = Path("data/cameras.db.antes_limpeza")

# Headers para evitar bloqueios
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def validar_camera(camera):
    cam_id, nome, url, tipo = camera
    
    # BLINDAGEM: Ignora URLs relativas (proxies locais) para não apagar por engano
    if url.startswith('/api/') or url.startswith('/'):
        return cam_id, True, "URL relativa (ignorada na auditoria)"
    
    try:
        # Cria um client para a requisição
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            # Define o Referer com base no domínio
            referer = f"https://{url.split('/')[2]}/"
            headers = {"User-Agent": USER_AGENT, "Referer": referer}
            
            if tipo == 'hls':
                resp = await client.get(url, headers=headers, follow_redirects=True)
                if resp.status_code == 200 and "#EXTM3U" in resp.text[:200]:
                    return cam_id, True, "OK"
                return cam_id, False, f"HTTP {resp.status_code} ou sem #EXTM3U"
            else:
                # Para MJPEG, Imagem e Video, lemos apenas os primeiros bytes
                async with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "").lower()
                        if "text/html" in content_type:
                            return cam_id, False, "HTML retornado no lugar de mídia"
                        
                        # Lê os primeiros 1024 bytes
                        try:
                            async for chunk in resp.aiter_bytes(chunk_size=1024):
                                if len(chunk) > 0:
                                    return cam_id, True, "OK"
                                break
                        except Exception:
                            return cam_id, False, "Falha ao ler bytes"
                    return cam_id, False, f"HTTP {resp.status_code}"
    except Exception as e:
        return cam_id, False, str(e)[:50]


async def main():
    if not DB_PATH.exists():
        print("❌ Banco de dados não encontrado.")
        return

    # Backup
    print(f"💾 Criando backup em {BACKUP_PATH}...")
    shutil.copy2(DB_PATH, BACKUP_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Pega câmeras que não são do Tomarigi (já removido) e que têm tipo_stream válido
    cursor.execute("""
        SELECT id, nome, stream_url, tipo_stream 
        FROM cameras 
        WHERE tipo_stream IN ('hls', 'mjpeg', 'imagem', 'video')
        AND stream_url NOT LIKE '%youtube%'
        AND stream_url NOT LIKE '%iframe%'
    """)
    cameras = cursor.fetchall()
    conn.close()

    print(f"🔍 Iniciando auditoria de {len(cameras)} câmeras...")
    
    # Roda as validações em paralelo (10 por vez)
    sem = asyncio.Semaphore(10)
    
    async def sem_validar(cam):
        async with sem:
            return await validar_camera(cam)
    
    resultados = await asyncio.gather(*(sem_validar(cam) for cam in cameras))
    
    mortas = [res[0] for res in resultados if not res[1]]
    vivas = len(resultados) - len(mortas)
    
    print(f"\n📊 Resultado da Auditoria:")
    print(f"   ✅ Vivas: {vivas}")
    print(f"   ❌ Mortas: {len(mortas)}")
    
    if mortas:
        print("\nExemplos de câmeras mortas:")
        for res in resultados:
            if not res[1]:
                print(f"  - ID {res[0]}: {res[2]}")
                
        # Pergunta se quer deletar
        resposta = input(f"\n⚠️ Deseja remover {len(mortas)} câmeras mortas? (s/N): ")
        if resposta.lower() == 's':
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM cameras WHERE id IN ({','.join(['?']*len(mortas))})", mortas)
            conn.commit()
            print("🗑️ Limpeza concluída!")
            print("🗜️ Otimizando banco (VACUUM)...")
            cursor.execute("VACUUM")
            conn.commit()
            conn.close()
            print("✅ Banco otimizado e enxuto!")
        else:
            print("❌ Limpeza cancelada. O banco permanece intacto.")
    else:
        print("🎉 Todas as câmeras estão vivas e funcionando!")

if __name__ == "__main__":
    asyncio.run(main())
