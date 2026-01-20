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
    # Procura estritamente o padrão NNN/AAAA (Ex: 007/2026)
    match = re.search(r'(\d+)/(\d{4})', texto)
    if match:
        return int(match.group(2)), int(match.group(1)) # Retorna (2026, 7) para ordenar
    return 0, 0

def main():
    print("Acessando o site...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(URL_ALVO, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        enviar_telegram(f"Erro ao acessar site: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    todos_editais = []
    ids_encontrados_agora = set()
    
    # Regex flexível: Pega qualquer coisa que pareça "000/202X"
    padrao_numero = re.compile(r'\d+/\d{4}')

    # Varre TODOS os links da página
    for link in soup.find_all('a', href=True):
        href = link['href']
        texto_original = link.get_text(" ", strip=True) # " " evita palavras coladas
        
        # A MÁGICA: Se tiver "007/2026" no texto, é vaga! (Ignora se tem 'edital' ou não)
        if padrao_numero.search(texto_original):
            
            if not href.startswith("http"):
                href = f"https://www.santacruz.rs.gov.br{href}"
            
            # Limpa o título (tira espaços duplos)
            titulo = " ".join(texto_original.split())
            
            edital = {
                'id': href, # Usamos o link como ID único
                'titulo': titulo,
                'ordem': extrair_numero_ano(titulo)
            }
            
            # Evita duplicatas (links repetidos na página)
            if href not in ids_encontrados_agora:
                todos_editais.append(edital)
                ids_encontrados_agora.add(href)

    # Ordena a lista completa: O mais novo (2026) fica em cima
    todos_editais.sort(key=lambda x: x['ordem'], reverse=True)

    # --- LÓGICA DE SEPARAÇÃO ---
    vagas_memoria = carregar_vistas()
    lista_novas = []
    
    for edital in todos_editais:
        if edital['id'] not in vagas_memoria:
            lista_novas.append(edital)

    # --- LISTA DE ANTERIORES ---
    # Pega simplesmente os 3 primeiros da lista GERAL ordenada
    # (Ignorando se são novos ou velhos, queremos mostrar os últimos publicados)
    lista_anteriores = todos_editais[:3]

    # Remove da lista de anteriores o que já estiver na lista de novas (para não repetir)
    ids_novas = [n['id'] for n in lista_novas]
    lista_anteriores = [a for a in lista_anteriores if a['id'] not in ids_novas]

    # --- MONTAGEM DA MENSAGEM ---
    
    msg = "---Vagas novas---\n\n"

    if lista_novas:
        for n in lista_novas:
            msg += f"{n['titulo']}\nLink: {n['id']}\n\n"
    else:
        msg += "SEM NOVAS VAGAS\n\n"

    msg += "---Anteriores---\n"
    
    if lista_anteriores:
        for a in lista_anteriores:
            msg += f"{a['titulo']}\n"
    elif not lista_novas: 
        # Só diz que não achou nada se não tiver nem novas nem anteriores
        msg += "Nenhuma vaga recente encontrada (Site mudou?)\n"

    # --- ENVIO ---
    
    agora_utc = datetime.now(timezone.utc)
    eh_horario_relatorio = (agora_utc.hour == 11) # 08h Brasil
    eh_manual = (EVENT_NAME == 'workflow_dispatch')
    tem_novidade = len(lista_novas) > 0

    # Envia se tiver novidade OU for horário de relatório OU for teste manual
    if tem_novidade or eh_manual or eh_horario_relatorio:
        print(f"Enviando. Novas: {len(lista_novas)}. Total encontradas: {len(todos_editais)}")
        enviar_telegram(msg)
        
        # Salva tudo o que viu hoje na memória
        salvar_vistas(vagas_memoria.union(ids_encontrados_agora))
    else:
        print("Silêncio.")

if __name__ == "__main__":
    main()
