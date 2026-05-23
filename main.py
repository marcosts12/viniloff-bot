"""
VinilOFF — Canal Spy
=====================
Monitora o canal @feirinhavinil (e outros canais de vinil),
intercepta os links da Amazon, substitui pela tag viniloff-20
e reposta no @viniloff_br com layout próprio.

COMO CONFIGURAR:
1. pip install telethon requests
2. Obtenha API ID e HASH em: https://my.telegram.org
   - Faça login → API development tools → Create application
3. Preencha as configurações abaixo
4. python viniloff_spy.py
   - Na primeira vez vai pedir seu número e código de verificação
   - Isso é normal — autentica como usuário, não como bot

IMPORTANTE:
- Use com responsabilidade
- Apenas canais públicos
- Sempre adicione sua marca ao repostar
"""

import subprocess, sys
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "telethon", "requests"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

import re
import asyncio
import requests
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityUrl, MessageEntityTextUrl

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES
# ─────────────────────────────────────────────

# Obtenha em: https://my.telegram.org → API development tools
TELEGRAM_API_ID   = 39188583          # número inteiro
TELEGRAM_API_HASH = "97c631ef6f467be13e810dd1fdf04b05"

# Bot do VinilOFF
TELEGRAM_BOT_TOKEN = "8944782842:AAHMfyHMKSijzbby1lc-hNplMMGPu7BnP4s"
TELEGRAM_CHAT_ID   = 7484525336
CANAL_DESTINO      = "@viniloff_br"
AFILIADO_ID        = "viniloff-20"

# Canais para monitorar (só canais públicos)
CANAIS_MONITORAR = [
    "@feirinhavinil",
    "@vinilbarato",
    # Adicione mais canais aqui
]

# Palavras-chave para filtrar (só reposta se contiver alguma)
# Deixe vazio [] para repostar tudo
KEYWORDS = ["vinil", "vinyl", "lp ", "disco", "amazon"]

# ─────────────────────────────────────────────
#  FUNÇÕES
# ─────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}", flush=True)


def link_afiliado(asin):
    return f"https://www.amazon.com.br/dp/{asin}?tag={AFILIADO_ID}"


def extrair_asin(url):
    """Extrai ASIN de URL da Amazon"""
    padroes = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'asin=([A-Z0-9]{10})',
        r'amazon\.com\.br/([A-Z0-9]{10})',
    ]
    for padrao in padroes:
        m = re.search(padrao, url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def extrair_preco(texto):
    """Extrai preços do texto"""
    precos = []
    for m in re.finditer(r'R\$\s*(\d{1,4})[,.](\d{2})', texto):
        precos.append(float(f"{m.group(1)}.{m.group(2)}"))
    return precos


def extrair_urls(texto):
    """Extrai todas as URLs do texto"""
    return re.findall(r'https?://[^\s\)\]\>\"]+', texto)


def substituir_links_afiliado(texto):
    """
    Substitui todos os links da Amazon no texto pela versão com tag viniloff-20.
    Retorna (novo_texto, lista_de_asins_encontrados)
    """
    asins_encontrados = []
    novo_texto = texto

    urls = extrair_urls(texto)
    for url in urls:
        if 'amazon.com.br' in url or 'amzn' in url.lower():
            asin = extrair_asin(url)
            if asin:
                novo_link = link_afiliado(asin)
                novo_texto = novo_texto.replace(url, novo_link)
                asins_encontrados.append(asin)
                log(f"  Link substituído: {asin} → tag={AFILIADO_ID}")
            else:
                # Não achou ASIN mas é link da Amazon — adiciona tag
                if '?' in url:
                    novo_link = f"{url}&tag={AFILIADO_ID}"
                else:
                    novo_link = f"{url}?tag={AFILIADO_ID}"
                novo_texto = novo_texto.replace(url, novo_link)
                log(f"  Tag adicionada ao link: {url[:50]}...")

    return novo_texto, asins_encontrados


def enviar_telegram(msg, chat_id=None, parse_mode="HTML"):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id or TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            },
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        log(f"Telegram erro: {e}")
        return False


def postar_no_canal(texto_original, asins, canal_origem):
    """Formata e posta no @viniloff_br"""

    # Substitui links por versão afiliada
    novo_texto, _ = substituir_links_afiliado(texto_original)

    # Remove menções ao canal de origem
    for canal in CANAIS_MONITORAR:
        novo_texto = novo_texto.replace(canal, "")
        novo_texto = novo_texto.replace(canal.replace("@", ""), "")

    # Remove "Forwarded from" se houver
    novo_texto = re.sub(r'Forwarded from.*?\n', '', novo_texto)

    # Limpa espaços extras
    novo_texto = re.sub(r'\n{3,}', '\n\n', novo_texto).strip()

    # Posta no canal
    url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url_api, json={
        "chat_id": CANAL_DESTINO,
        "text": novo_texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=10)

    if r.status_code == 200:
        log(f"  ✅ Postado no {CANAL_DESTINO}!")

        # Avisa no privado
        enviar_telegram(
            f"🔁 <b>Repost do {canal_origem}</b>\n\n"
            f"ASINs: {', '.join(asins) if asins else 'nenhum'}\n"
            f"Links substituídos com <code>tag={AFILIADO_ID}</code>\n\n"
            f"<i>{datetime.now().strftime('%d/%m %H:%M')}</i>"
        )
        return True
    else:
        log(f"  ❌ Erro ao postar: {r.status_code} {r.text[:100]}")
        return False


def contem_keyword(texto):
    """Verifica se o texto contém alguma palavra-chave de vinil"""
    if not KEYWORDS:
        return True
    texto_lower = texto.lower()
    return any(kw.lower() in texto_lower for kw in KEYWORDS)


def contem_link_amazon(texto):
    """Verifica se o texto contém link da Amazon"""
    return 'amazon.com.br' in texto or 'amzn.to' in texto or 'amzn.com' in texto


# ─────────────────────────────────────────────
#  CLIENTE TELETHON
# ─────────────────────────────────────────────

async def main():
    # Cria cliente Telethon (autentica como usuário)
    client = TelegramClient("viniloff_spy", TELEGRAM_API_ID, TELEGRAM_API_HASH)

    await client.start()
    log("✅ Conectado ao Telegram como usuário!")
    log(f"Monitorando: {', '.join(CANAIS_MONITORAR)}")
    log(f"Destino: {CANAL_DESTINO}")

    enviar_telegram(
        f"👀 <b>VinilOFF Spy ativo!</b>\n\n"
        f"Monitorando:\n" +
        "\n".join([f"• {c}" for c in CANAIS_MONITORAR]) +
        f"\n\nDestino: {CANAL_DESTINO}\n"
        f"Tag: {AFILIADO_ID}\n\n"
        f"<i>Toda promoção de vinil será repostada com seu link!</i>"
    )

    @client.on(events.NewMessage(chats=CANAIS_MONITORAR))
    async def handler(event):
        try:
            msg = event.message
            texto = msg.text or msg.message or ""

            if not texto:
                return

            canal_origem = event.chat.username or str(event.chat_id)
            log(f"Nova mensagem em @{canal_origem}: {texto[:80]}...")

            # Filtra por keyword e link Amazon
            if not contem_keyword(texto):
                log("  Ignorado — sem keyword de vinil")
                return

            if not contem_link_amazon(texto):
                log("  Ignorado — sem link Amazon")
                return

            log("  ✅ Mensagem relevante! Processando...")

            # Extrai ASINs
            urls = extrair_urls(texto)
            asins = []
            for url in urls:
                asin = extrair_asin(url)
                if asin:
                    asins.append(asin)

            # Posta no canal
            postar_no_canal(texto, asins, f"@{canal_origem}")

        except Exception as e:
            log(f"Erro ao processar mensagem: {e}")

    log("👂 Escutando novas mensagens...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
