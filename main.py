import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime, timezone

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
ARQUIVO_MEMORIA = "vagas_vistas.txt"
URL_BASE = "https://www.santacruz.rs.gov.br/_pssonline/"
EVENT_NAME = os.environ.get('GITHUB_EVENT_NAME')

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Credenciais não configuradas.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensagem}
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
    match = re.search(r'(\d+)/(\d{4})', texto)
    if match:
        return int(match.group(2)), int(match.group(1)) # Ano, Número
    return 0, 0

def main():
    print("Acessando o site...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    try:
        response = requests.get(URL_BASE, headers=headers, timeout=40, verify=False)
        response.encoding = response.apparent_encoding
    except Exception as e:
        enviar_telegram(f"Erro ao acessar site: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    todos_editais = []
    ids_encontrados_agora = set()
    
    # 1. Encontra cada caixa de vaga (div class="card-body")
    cartoes = soup.find_all('div', class_='card-body')

    for card in cartoes:
        # Pega o Título
        titulo_tag = card.find('h5', class_='card-title')
        if not titulo_tag:
            continue
            
        titulo_texto = " ".join(titulo_tag.get_text().split())
        
        # Pega o Botão "Acessar" e extrai o link do JavaScript
        botao = card.find('input', attrs={'value': re.compile(r'Acessar', re.I)})
        link_final = URL_BASE 
        
        if botao and botao.get('onclick'):
            match_link = re.search(r"location='(.*?)'", botao['onclick'])
            if match_link:
                parametro = match_link.group(1)
                link_final = f"{URL_BASE}{parametro}"

        # Se tiver número de edital (ex: 007/2026), adiciona na lista
        if extrair_numero_ano(titulo_texto) != (0,0):
            edital = {
                'id': titulo_texto, # Identificador único
                'titulo': titulo_texto,
                'link': link_final,
                'ordem': extrair_numero_ano(titulo_texto)
            }
            todos_editais.append(edital)
            ids_encontrados_agora.add(titulo_texto)

    # 2. Ordena (Mais recentes primeiro)
    todos_editais.sort(key=lambda x: x['ordem'], reverse=True)

    # 3. Separa Novas vs Antigas
    vagas_memoria = carregar_vistas()
    lista_novas = []
    
    for edital in todos_editais:
        if edital['id'] not in vagas_memoria:
            lista_novas.append(edital)

    # 4. Define "Anteriores" (Top 3 que não são as novas)
    lista_anteriores = todos_editais[:3]
    ids_novas = [n['id'] for n in lista_novas]
    lista_anteriores = [a for a in lista_anteriores if a['id'] not in ids_novas]

    # --- MONTAGEM DA MENSAGEM ---
    msg = "---Vagas novas---\n\n"

    if lista_novas:
        for n in lista_novas:
            msg += f"{n['titulo']}\nLink: {n['link']}\n\n"
    else:
        msg += "SEM NOVAS VAGAS\n\n"

    msg += "---Anteriores---\n"
    
    if lista_anteriores:
        for a in lista_anteriores:
            msg += f"{a['titulo']}\n"
    elif not todos_editais:
        msg += "Nenhum edital encontrado (Site mudou?)\n"

    # --- ENVIO ---
    # Envia se: Tiver novidade OU for horário do relatório (11h UTC = 08h Brasil) OU for Manual
    agora_utc = datetime.now(timezone.utc)
    eh_horario_relatorio = (agora_utc.hour == 11) 
    eh_manual = (EVENT_NAME == 'workflow_dispatch')
    tem_novidade = len(lista_novas) > 0

    if tem_novidade or eh_manual or eh_horario_relatorio:
        print(f"Enviando telegram. Novas: {len(lista_novas)}")
        enviar_telegram(msg)
        # Só atualiza a memória se tiver novas, para não "esquecer" nada por acidente
        salvar_vistas(vagas_memoria.union(ids_encontrados_agora))
    else:
        print("Silêncio (Fora de horário e sem novidades).")

if __name__ == "__main__":
    main()
