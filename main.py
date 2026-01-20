import requests
from bs4 import BeautifulSoup
import os

# Configurações do Telegram (Vêm das "Secrets" do GitHub)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# Arquivo que serve de memória
ARQUIVO_MEMORIA = "vagas_vistas.txt"
URL_ALVO = "https://www.santacruz.rs.gov.br/_pssonline/"

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Erro: Credenciais do Telegram não encontradas.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
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

def main():
    print("Acessando o site...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(URL_ALVO, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Erro ao acessar site: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Lógica de extração: Procura links que pareçam ser de editais
    # Adaptado para pegar links na área principal de conteúdo
    novas_vagas = []
    vagas_atuais = set()
    
    # Procura todos os links da página
    for link in soup.find_all('a', href=True):
        href = link['href']
        texto = link.get_text(strip=True)
        
        # Filtro: Pega apenas links que contêm 'edital' ou parecem ser um PSS
        # Ajuste este filtro se o site mudar a forma de nomear
        if "edital" in href.lower() or "pss" in texto.lower() or "processo seletivo" in texto.lower():
            
            # Cria uma "assinatura" única para a vaga (pode ser o link completo)
            # Se o link for relativo, completa ele
            if not href.startswith("http"):
                href = f"https://www.santacruz.rs.gov.br{href}"
            
            id_vaga = href 
            vagas_atuais.add(id_vaga)
            
            vistas = carregar_vistas()
            
            if id_vaga not in vistas:
                novas_vagas.append(f"📄 *{texto}*\n[Link para o edital]({href})")

    if novas_vagas:
        print(f"Encontradas {len(novas_vagas)} novas vagas!")
        msg = f"🚨 *Nova(s) vaga(s) encontrada(s) em Santa Cruz:*\n\n" + "\n\n".join(novas_vagas)
        enviar_telegram(msg)
        
        # Atualiza a memória adicionando as novas (mantendo as antigas para histórico)
        todas_vistas = vistas.union(vagas_atuais)
        salvar_vistas(todas_vistas)
    else:
        print("Nenhuma vaga nova encontrada.")

if __name__ == "__main__":
    main()