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
    match = re.search(r'(\d+)/(\d{4})', texto)
    if match:
        return int(match.group(2)), int(match.group(1)) # Ano, Número
    return 0, 0

def main():
    print("Acessando o site...")
    # Header simulando um navegador real para evitar bloqueios
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    try:
        # verify=False ajuda se o certificado SSL da prefeitura for antigo (comum em gov.br)
        response = requests.get(URL_ALVO, headers=headers, timeout=40, verify=False) 
        response.raise_for_status()
        
        # Tenta decodificar corretamente (sites antigos as vezes usam latin-1)
        response.encoding = response.apparent_encoding
        
    except Exception as e:
        enviar_telegram(f"Erro ao acessar site: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    todos_editais = []
    ids_encontrados_agora = set()
    
    # Regex: Procura estritamente NNN/AAAA
    padrao_numero = re.compile(r'\d+/\d{4}')

    # NOVA ESTRATÉGIA: Busca Texto primeiro, Link depois
    # Procura todos os pedaços de texto visíveis na página
    elementos_texto = soup.find_all(string=padrao_numero)

    for texto_node in elementos_texto:
        texto_limpo = " ".join(texto_node.strip().split())
        
        # Se o texto for muito curto, pega o pai para garantir que pegamos a descrição completa
        # Ex: as vezes o texto é só "007/2026" e o "Médico" está num span ao lado
        elemento_pai = texto_node.parent
        titulo_completo = " ".join(elemento_pai.get_text(" ", strip=True).split())

        # Agora caçamos o link associado a esse texto
        # Procuramos um link (<a>) no próprio elemento ou nos pais (subindo a escada do HTML)
        link_encontrado = None
        cursor = elemento_pai
        
        # Sobe até 4 níveis (span -> div -> td -> tr) procurando um <a href>
        for _ in range(4):
            if not cursor: break
            
            # Verifica se o próprio cursor é um link
            if cursor.name == 'a' and cursor.get('href'):
                link_encontrado = cursor.get('href')
                break
            
            # Verifica se tem um link DENTRO do cursor
            busca_link = cursor.find('a', href=True)
            if busca_link:
                link_encontrado = busca_link['href']
                break
            
            cursor = cursor.parent

        if link_encontrado:
            if not link_encontrado.startswith("http"):
                link_encontrado = f"https://www.santacruz.rs.gov.br{link_encontrado}"
            
            # ID único baseado no Título + Link (para diferenciar editais com mesmo link)
            id_unico = f"{texto_limpo}||{link_encontrado}"
            
            edital = {
                'id': id_unico, 
                'titulo': titulo_completo,
                'link': link_encontrado,
                'ordem': extrair_numero_ano(texto_limpo)
            }
            
            # Adiciona se não for duplicado
            if id_unico not in ids_encontrados_agora:
                todos_editais.append(edital)
                ids_encontrados_agora.add(id_unico)

    # Ordena
    todos_editais.sort(key=lambda x: x['ordem'], reverse=True)

    # --- SEPARAÇÃO ---
    vagas_memoria = carregar_vistas()
    lista_novas = []
    
    for edital in todos_editais:
        if edital['id'] not in vagas_memoria:
            lista_novas.append(edital)

    # --- ANTERIORES (Top 3 geral) ---
    lista_anteriores = todos_editais[:3]
    # Remove duplicatas se elas já estiverem nas novas
    ids_novas = [n['id'] for n in lista_novas]
    lista_anteriores = [a for a in lista_anteriores if a['id'] not in ids_novas]

    # --- ENVIO ---
    msg = "---Vagas novas---\n\n"

    if lista_novas:
        for n in lista_novas:
            msg += f"{n['titulo']}\nLink: {n['link']}\n\n"
    else:
        msg += "SEM NOVAS VAGAS\n\n"

    msg += "---Anteriores---\n"
    
    if lista_anteriores:
        for a in lista_anteriores:
            # Mostra só o título para ficar limpo
            msg += f"{a['titulo']}\n"
    elif not todos_editais:
        msg += "Nenhum edital encontrado (Site inacessível ou layout mudou drasticamente).\n"

    # Envia
    agora_utc = datetime.now(timezone.utc)
    eh_horario_relatorio = (agora_utc.hour == 11) 
    eh_manual = (EVENT_NAME == 'workflow_dispatch')
    tem_novidade = len(lista_novas) > 0

    if tem_novidade or eh_manual or eh_horario_relatorio:
        print(f"Enviando. Novas: {len(lista_novas)}. Total detetadas: {len(todos_editais)}")
        enviar_telegram(msg)
        salvar_vistas(vagas_memoria.union(ids_encontrados_agora))
    else:
        print(f"Silêncio. Total detetadas: {len(todos_editais)}")

if __name__ == "__main__":
    main()
