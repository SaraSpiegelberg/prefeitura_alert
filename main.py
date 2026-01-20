import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime, timezone

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
ARQUIVO_MEMORIA = "vagas_vistas.txt"
URL_ALVO = "https://www.santacruz.rs.gov.br/_pssonline/"
EVENT_NAME = os.environ.get('GITHUB_EVENT_NAME')

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Credenciais não configuradas.")
        return
    # O Telegram tem limite de 4096 caracteres. Se ficar muito grande, cortamos.
    if len(mensagem) > 4000:
        mensagem = mensagem[:4000] + "\n... (lista cortada por tamanho)"
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensagem} # Tirei o Markdown para evitar erros de formatação no layout
    requests.post(url, data=data)

def carregar_vistas():
    if not os.path.exists(ARQUIVO_MEMORIA):
        return set()
    with open(ARQUIVO_MEMORIA, "r") as f:
        return set(line.strip() for line in f)

def salvar_vistas(vistas):
    with open(ARQUIVO_MEMORIA, "w") as f:
        for v in vistas:
            f.write(f"{v}\n")

def extrair_numero_ano(texto):
    # Tenta achar algo como "007/2026" ou "7/2026" para ordenar
    match = re.search(r'(\d+)/(\d{4})', texto)
    if match:
        numero = int(match.group(1))
        ano = int(match.group(2))
        return ano, numero
    return 0, 0 # Se não achar, joga pro final da lista

def main():
    print("Acessando o site...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(URL_ALVO, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        enviar_telegram(f"⚠️ Erro ao acessar o site: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Listas para organizar
    todos_editais_pagina = [] 
    vagas_vistas_ids = carregar_vistas()
    ids_encontrados_agora = set()

    # Regex simples para identificar editais
    padrao_edital = re.compile(r'\d+/\d{4}')

    for link in soup.find_all('a', href=True):
        href = link['href']
        texto_original = link.get_text(strip=True)
        
        # Filtro: Pega se tiver número de edital OU palavras chave
        if padrao_edital.search(texto_original) or "edital" in href.lower() or "pss" in texto_original.lower():
            
            if not href.startswith("http"):
                href = f"https://www.santacruz.rs.gov.br{href}"
            
            # Limpeza do Texto para ficar bonito (Ex: Tira espaços extras)
            titulo = " ".join(texto_original.split())
            
            # Cria um objeto para facilitar a ordenação
            edital = {
                'id': href,
                'titulo': titulo,
                'link': href,
                'ordem': extrair_numero_ano(titulo) # Usado para ordenar (2026, 7)
            }
            
            todos_editais_pagina.append(edital)
            ids_encontrados_agora.add(href)

    # Ordena: Do ano/número maior para o menor (007/2026 vem antes de 006/2026)
    todos_editais_pagina.sort(key=lambda x: x['ordem'], reverse=True)

    # Separa em NOVAS e ANTERIORES
    lista_novas = []
    lista_anteriores = []

    for edital in todos_editais_pagina:
        if edital['id'] not in vagas_vistas_ids:
            lista_novas.append(edital)
        else:
            lista_anteriores.append(edital)

    # --- MONTAGEM DA MENSAGEM ---
    
    deve_enviar = False
    
    # Cabeçalho
    msg = "------------Vagas Novas--------------------\n\n"

    # Bloco 1: Vagas Novas
    if lista_novas:
        deve_enviar = True # Se tem nova, TEM que enviar
        for n in lista_novas:
            msg += f"🔥 {n['titulo']}\nLink: {n['link']}\n\n"
    else:
        msg += "NENHUMA VAGA NOVA HOJE\n\n"

    # Bloco 2: Anteriores (Limitado a 15 para não spammar demais)
    msg += "----------- ANTERIORES---------------------\n"
    if lista_anteriores:
        for a in lista_anteriores[:15]:
            msg += f"{a['titulo']}\n"
    else:
        msg += "(Nenhum histórico recente encontrado)\n"

    # --- LÓGICA DE ENVIO ---
    
    # Verifica horário (08:00 BRT = 11:00 UTC)
    agora_utc = datetime.now(timezone.utc)
    eh_horario_relatorio = (agora_utc.hour == 11)
    eh_manual = (EVENT_NAME == 'workflow_dispatch')

    # Envia SE: (Tiver Novas) OU (For Manual) OU (For Relatório das 08h)
    if deve_enviar or eh_manual or eh_horario_relatorio:
        print("Enviando mensagem para o Telegram...")
        enviar_telegram(msg)
        
        # Atualiza a memória
        if lista_novas:
            nova_memoria = vagas_vistas_ids.union(ids_encontrados_agora)
            salvar_vistas(nova_memoria)
    else:
        print("Nada novo e fora de horário. Silêncio.")

if __name__ == "__main__":
    main()
