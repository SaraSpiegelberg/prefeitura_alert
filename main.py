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
    
    # Envia como texto puro (sem Markdown) para evitar quebrar a formatação
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
    # Extrai números para ordenar corretamente (Ex: 007/2026 > 006/2026)
    match = re.search(r'(\d+)/(\d{4})', texto)
    if match:
        return int(match.group(2)), int(match.group(1)) # Ano, Número
    return 0, 0

def limpar_titulo(texto):
    # Remove espaços extras e quebras de linha
    return " ".join(texto.split())

def main():
    print("Acessando o site...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(URL_ALVO, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        enviar_telegram(f"Erro ao acessar site: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    todos_editais = []
    ids_encontrados_agora = set()
    
    padrao_edital = re.compile(r'\d+/\d{4}')

    # 1. Coleta TUDO o que tem na página
    for link in soup.find_all('a', href=True):
        href = link['href']
        texto_original = link.get_text(strip=True)
        
        if padrao_edital.search(texto_original) or "edital" in href.lower() or "pss" in texto_original.lower():
            if not href.startswith("http"):
                href = f"https://www.santacruz.rs.gov.br{href}"
            
            titulo = limpar_titulo(texto_original)
            
            edital = {
                'id': href,
                'titulo': titulo,
                'ordem': extrair_numero_ano(titulo)
            }
            
            # Evita duplicatas na lista
            if href not in ids_encontrados_agora:
                todos_editais.append(edital)
                ids_encontrados_agora.add(href)

    # 2. Ordena do mais recente para o mais antigo
    todos_editais.sort(key=lambda x: x['ordem'], reverse=True)

    # 3. Separa o que é NOVO do que é VELHO
    vagas_memoria = carregar_vistas()
    lista_novas = []
    
    for edital in todos_editais:
        if edital['id'] not in vagas_memoria:
            lista_novas.append(edital)

    # 4. Define a lista de ANTERIORES
    # Lógica: Pega os Top 3 da página que NÃO estão na lista de novas.
    # Se não tiver novas, pega simplesmente os Top 3 da página.
    ids_novas = [n['id'] for n in lista_novas]
    lista_anteriores = [e for e in todos_editais if e['id'] not in ids_novas]
    
    # Pega apenas os 3 primeiros da lista de anteriores
    lista_anteriores = lista_anteriores[:3]

    # --- MONTAGEM DA MENSAGEM (O Visual que você pediu) ---
    
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
    else:
        # Só acontece se o site estiver vazio ou der erro de leitura
        msg += "Nenhuma vaga encontrada no site.\n"

    # --- ENVIO ---
    
    # Verifica horários
    agora_utc = datetime.now(timezone.utc)
    eh_horario_relatorio = (agora_utc.hour == 11) # 08h Brasil
    eh_manual = (EVENT_NAME == 'workflow_dispatch')
    tem_novidade = len(lista_novas) > 0

    if tem_novidade or eh_manual or eh_horario_relatorio:
        print("Enviando Telegram...")
        enviar_telegram(msg)
        
        # Atualiza a memória com TUDO o que viu na página hoje
        salvar_vistas(vagas_memoria.union(ids_encontrados_agora))
    else:
        print("Sem novidades e fora de horário.")

if __name__ == "__main__":
    main()
