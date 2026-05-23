"""
VinilOFF — Keepa Bridge Bot
============================
Intercepta alertas do Keepa no Telegram e reposta
automaticamente no canal @viniloff_br com link de afiliado.

COMO CONFIGURAR:
1. pip install requests
2. Configure as variáveis abaixo
3. No Keepa: Settings → Notifications → Telegram
   - Conecte ao seu bot @viniloff_bot
4. python viniloff_keepa_bridge.py

COMO FUNCIONA:
- Keepa detecta queda de preço
- Keepa manda mensagem no seu Telegram
- Este script intercepta essa mensagem
- Extrai o ASIN e preço automaticamente
- Gera link com tag=viniloff-20
- Posta no canal @viniloff_br com formato bonito
"""

import subprocess, sys
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "requests"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

import requests
import re
import time
import json
import os
from datetime import datetime

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES
# ─────────────────────────────────────────────

TELEGRAM_TOKEN   = "8944782842:AAHMfyHMKSijzbby1lc-hNplMMGPu7BnP4s"       # token do @viniloff_bot
TELEGRAM_CHAT_ID = 7484525336     # seu ID pessoal
CANAL_USERNAME   = "@viniloff_br"          # canal público
AFILIADO_ID      = "viniloff-20"           # seu ID de afiliado

# ID do bot do Keepa no Telegram — é sempre esse
KEEPA_BOT_ID     = "476000"

# Arquivo para evitar repostar o mesmo alerta duas vezes
ARQUIVO_PROCESSADOS = "alertas_processados.json"

# ─────────────────────────────────────────────
#  FUNÇÕES
# ─────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}", flush=True)


def link_afiliado(asin):
    return f"https://www.amazon.com.br/dp/{asin}?tag={AFILIADO_ID}"


def carregar_processados():
    if os.path.exists(ARQUIVO_PROCESSADOS):
        with open(ARQUIVO_PROCESSADOS, "r") as f:
            return set(json.load(f))
    return set()


def salvar_processados(ids):
    with open(ARQUIVO_PROCESSADOS, "w") as f:
        json.dump(list(ids)[-500:], f)  # mantém só os últimos 500


def enviar_telegram(msg, chat_id=None):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        log(f"Telegram erro: {e}")
        return False


def postar_no_canal(nome, asin, preco_atual, preco_anterior=None, desconto=None, img_url=None):
    """Posta promoção formatada no canal @viniloff_br"""
    url_prod = link_afiliado(asin)

    if preco_anterior and preco_anterior > preco_atual:
        economia = preco_anterior - preco_atual
        pct      = round(((preco_anterior - preco_atual) / preco_anterior) * 100)
        fogo     = "🔥🔥🔥" if pct >= 30 else "🔥🔥" if pct >= 20 else "🔥"
        preco_linha = (
            f"<s>R$ {preco_anterior:.2f}</s>  →  <b>R$ {preco_atual:.2f}</b>\n"
            f"💸 Economia de <b>R$ {economia:.2f} ({pct}% OFF)</b>"
        )
    else:
        fogo = "🔥"
        preco_linha = f"<b>R$ {preco_atual:.2f}</b>"

    caption = (
        f"{fogo} <b>VINIL EM PROMOÇÃO!</b>\n\n"
        f"🎵 <b>{nome}</b>\n\n"
        f"{preco_linha}\n\n"
        f"🛒 <a href=\"{url_prod}\">Comprar →</a>"
    )

    # Tenta com foto
    if img_url:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                json={"chat_id": CANAL_USERNAME, "photo": img_url,
                      "caption": caption, "parse_mode": "HTML"},
                timeout=15
            )
            if r.status_code == 200:
                log(f"  ✅ Postado com foto no {CANAL_USERNAME}!")
                return True
        except Exception:
            pass

    # Fallback sem foto
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CANAL_USERNAME, "text": caption,
              "parse_mode": "HTML", "disable_web_page_preview": False},
        timeout=10
    )
    if r.status_code == 200:
        log(f"  ✅ Postado no canal {CANAL_USERNAME}!")
        return True
    log(f"  ❌ Erro: {r.text}")
    return False


def extrair_asin_da_url(texto):
    """Extrai ASIN de qualquer URL da Amazon"""
    padroes = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'asin=([A-Z0-9]{10})',
        r'/([A-Z0-9]{10})(?:\?|/|$)',
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            return match.group(1)
    return None


def extrair_preco(texto):
    """Extrai valor em R$ de um texto"""
    # Padrões: R$ 199,90 / R$199.90 / 199,90
    padroes = [
        r'R\$\s*(\d+)[,.](\d{2})',
        r'(\d+)[,.](\d{2})\s*(?:BRL|reais)',
        r'(\d{1,4})[,.](\d{2})',
    ]
    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            inteiro = match.group(1).replace('.', '').replace(',', '')
            decimal = match.group(2)
            return float(f"{inteiro}.{decimal}")
    return None


def processar_mensagem_keepa(texto, update_id):
    """
    Processa mensagem do Keepa e extrai dados do produto.
    
    Exemplos de mensagem do Keepa:
    - "Price drop! Product Name - Now: R$ 189,90 (was R$ 320,00) amazon.com.br/dp/ASIN"
    - "⚡ Price Alert: Product Name R$ 199,90 https://amazon.com.br/dp/ASIN"
    """
    log(f"Mensagem do Keepa: {texto[:100]}...")

    # Extrai ASIN
    asin = extrair_asin_da_url(texto)
    if not asin:
        log("  ASIN não encontrado na mensagem")
        return False

    log(f"  ASIN: {asin}")

    # Extrai preços — pega todos os valores monetários encontrados
    precos = []
    for match in re.finditer(r'R\$\s*(\d+)[,.](\d{2})', texto):
        val = float(f"{match.group(1)}.{match.group(2)}")
        precos.append(val)

    if not precos:
        # Tenta formato sem R$
        for match in re.finditer(r'\b(\d{2,4})[,.](\d{2})\b', texto):
            val = float(f"{match.group(1)}.{match.group(2)}")
            if 20 < val < 5000:
                precos.append(val)

    if not precos:
        log("  Preço não encontrado na mensagem")
        return False

    preco_atual    = min(precos)   # menor preço = preço atual (em promoção)
    preco_anterior = max(precos) if len(precos) > 1 else None

    log(f"  Preço atual: R$ {preco_atual:.2f}")
    if preco_anterior:
        log(f"  Preço anterior: R$ {preco_anterior:.2f}")

    # Extrai nome do produto — pega a primeira linha não vazia antes do preço
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    nome = "Disco de Vinil"
    for linha in linhas:
        # Ignora linhas que são só emojis, URLs ou preços
        if (len(linha) > 10
                and 'amazon' not in linha.lower()
                and 'keepa' not in linha.lower()
                and not linha.startswith('http')
                and not re.match(r'^[R\$\d\s,\.]+$', linha)):
            nome = linha[:80]
            break

    log(f"  Nome: {nome}")

    # Posta no canal
    postar_no_canal(
        nome=nome,
        asin=asin,
        preco_atual=preco_atual,
        preco_anterior=preco_anterior,
    )

    # Confirma no privado
    enviar_telegram(
        f"✅ <b>Alerta do Keepa processado!</b>\n\n"
        f"🎵 {nome}\n"
        f"📦 ASIN: <code>{asin}</code>\n"
        f"💰 R$ {preco_atual:.2f}\n\n"
        f"Postado no {CANAL_USERNAME} com link afiliado!"
    )
    return True


def escutar_mensagens():
    """Fica escutando mensagens no Telegram e processa alertas do Keepa"""
    ultimo_update = 0
    processados   = carregar_processados()

    log("👂 Escutando alertas do Keepa...")
    log(f"Canal: {CANAL_USERNAME} | Afiliado: {AFILIADO_ID}")

    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": ultimo_update + 1, "timeout": 30},
                timeout=35
            )

            if r.status_code != 200:
                time.sleep(10)
                continue

            updates = r.json().get("result", [])

            for update in updates:
                ultimo_update = update["update_id"]
                uid = str(update["update_id"])

                if uid in processados:
                    continue

                msg      = update.get("message", {})
                texto    = msg.get("text", "").strip()
                from_id  = msg.get("from", {}).get("id")
                chat_id  = str(msg.get("chat", {}).get("id", ""))

                # Só processa mensagens para você
                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                # Comandos do bot
                if texto.lower() == "/status":
                    enviar_telegram(
                        f"📊 <b>VinilOFF Keepa Bridge</b>\n\n"
                        f"✅ Online e escutando\n"
                        f"📨 Alertas processados: {len(processados)}\n"
                        f"📢 Canal: {CANAL_USERNAME}\n"
                        f"🔗 Afiliado: {AFILIADO_ID}\n\n"
                        f"<i>{datetime.now().strftime('%d/%m/%Y %H:%M')}</i>"
                    )
                    processados.add(uid)
                    continue

                elif texto.lower() == "/ajuda":
                    enviar_telegram(
                        f"🤖 <b>VinilOFF Keepa Bridge</b>\n\n"
                        f"Este bot intercepta alertas do Keepa e posta automaticamente no {CANAL_USERNAME}.\n\n"
                        f"<b>Como funciona:</b>\n"
                        f"1. Configure alertas no keepa.com\n"
                        f"2. Conecte o Keepa a este bot\n"
                        f"3. Quando um vinil cair de preço, o Keepa avisa aqui\n"
                        f"4. O bot reposta no canal com link de afiliado\n\n"
                        f"/status — ver status\n"
                        f"/testar ASIN PRECO — testar um post manual\n"
                        f"Ex: /testar B07Z74G6MR 189.90"
                    )
                    processados.add(uid)
                    continue

                elif texto.lower().startswith("/testar"):
                    # Permite testar manualmente: /testar B07Z74G6MR 189.90
                    partes = texto.split()
                    if len(partes) >= 3:
                        asin_teste  = partes[1].upper()
                        preco_teste = float(partes[2].replace(",", "."))
                        log(f"Teste manual: ASIN={asin_teste} Preço=R${preco_teste}")
                        postar_no_canal(
                            nome="Disco de Vinil — Teste",
                            asin=asin_teste,
                            preco_atual=preco_teste,
                            preco_anterior=preco_teste * 1.3,
                        )
                    else:
                        enviar_telegram("Uso: /testar ASIN PRECO\nEx: /testar B07Z74G6MR 189.90")
                    processados.add(uid)
                    continue

                # Verifica se é alerta do Keepa
                # O Keepa manda de um bot específico OU contém padrões reconhecíveis
                eh_keepa = (
                    str(from_id) == KEEPA_BOT_ID
                    or "keepa" in texto.lower()
                    or ("amazon" in texto.lower() and ("price" in texto.lower() or "drop" in texto.lower() or "alert" in texto.lower()))
                    or ("amazon.com.br" in texto.lower() and any(c.isdigit() for c in texto))
                )

                if eh_keepa and texto:
                    log(f"Alerta do Keepa detectado! Update #{uid}")
                    processar_mensagem_keepa(texto, uid)
                    processados.add(uid)
                    salvar_processados(processados)

        except Exception as e:
            log(f"Erro: {e}")
            time.sleep(15)


def main():
    log("🎵 VinilOFF Keepa Bridge iniciado!")
    log(f"Canal: {CANAL_USERNAME} | Tag: {AFILIADO_ID}")

    enviar_telegram(
        f"🎵 <b>VinilOFF Keepa Bridge ativo!</b>\n\n"
        f"Agora configure o Keepa para enviar alertas aqui.\n\n"
        f"<b>Como configurar o Keepa:</b>\n"
        f"1. Acesse keepa.com → Settings\n"
        f"2. Vá em Notifications → Telegram\n"
        f"3. Conecte ao @viniloff_bot\n"
        f"4. Quando um vinil cair de preço, posto no {CANAL_USERNAME} automaticamente!\n\n"
        f"Teste com: /testar B07Z74G6MR 189.90\n"
        f"/ajuda para ver todos os comandos"
    )

    escutar_mensagens()


if __name__ == "__main__":
    main()

