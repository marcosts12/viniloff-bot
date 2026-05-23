"""
VinilOFF — Bot com Descoberta Automática de Vinis
==================================================
Varre a categoria de vinis da Amazon Brasil, descobre os produtos
automaticamente e monitora quedas de preço via Telegram.

COMO USAR:
1. pip install requests beautifulsoup4
2. Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID abaixo
3. python viniloff_bot_auto.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
import random
from datetime import datetime
from urllib.parse import urljoin

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES
# ─────────────────────────────────────────────

TELEGRAM_TOKEN    = 8944782842:AAHMfyHMKSijzbby1lc-hNplMMGPu7BnP4s
TELEGRAM_CHAT_ID  = 7484525336

# Desconto mínimo para alertar (em %)
DESCONTO_MINIMO   = 15

# Intervalo entre varreduras completas (em minutos)
INTERVALO_MINUTOS = 60

# Quantas páginas da categoria varrer (cada página tem ~20 produtos)
PAGINAS_VARRER    = 5

# Arquivo de histórico
ARQUIVO_HISTORICO = "historico_viniloff.json"

# URLs das categorias de vinil na Amazon Brasil
CATEGORIAS = [
    {
        "nome": "Vinil — Todos",
        "url": "https://www.amazon.com.br/s?i=music&rh=n%3A19549018011&s=price-asc-rank"
    },
    {
        "nome": "Vinil — Pop",
        "url": "https://www.amazon.com.br/s?i=music&rh=n%3A19549018011%2Cn%3A6309293011&s=price-asc-rank"
    },
    {
        "nome": "Vinil — Rock",
        "url": "https://www.amazon.com.br/s?i=music&rh=n%3A19549018011%2Cn%3A6309285011&s=price-asc-rank"
    },
    {
        "nome": "Vinil — MPB",
        "url": "https://www.amazon.com.br/s?i=music&rh=n%3A19549018011%2Cn%3A6309271011&s=price-asc-rank"
    },
]

# ─────────────────────────────────────────────
#  CÓDIGO
# ─────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
]


def log(msg):
    print(f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}")


def headers_aleatorios():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def enviar_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log(f"Telegram erro: {e}")
        return False


def carregar_historico():
    if os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_historico(dados):
    with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def extrair_produtos_da_pagina(html):
    """Extrai todos os produtos de uma página de resultados da Amazon"""
    soup = BeautifulSoup(html, "html.parser")
    produtos = []

    # Cada produto na listagem da Amazon
    cards = soup.select("div[data-asin]:not([data-asin=''])")

    for card in cards:
        try:
            asin = card.get("data-asin", "").strip()
            if not asin or len(asin) < 5:
                continue

            # Nome do produto
            nome_el = card.select_one("h2 span, h2 a span")
            if not nome_el:
                continue
            nome = nome_el.get_text().strip()
            if not nome:
                continue

            # Preço atual
            preco_el = card.select_one(".a-price .a-offscreen")
            if not preco_el:
                continue
            preco_str = (preco_el.get_text()
                .replace("R$", "")
                .replace("\xa0", "")
                .replace(" ", "")
                .replace(".", "")
                .replace(",", ".")
                .strip()
            )
            try:
                preco = float(preco_str)
                if preco < 10 or preco > 5000:
                    continue
            except ValueError:
                continue

            # Preço original (se tiver desconto)
            preco_original_el = card.select_one(".a-text-price .a-offscreen")
            preco_original = None
            if preco_original_el:
                orig_str = (preco_original_el.get_text()
                    .replace("R$", "")
                    .replace("\xa0", "")
                    .replace(" ", "")
                    .replace(".", "")
                    .replace(",", ".")
                    .strip()
                )
                try:
                    preco_original = float(orig_str)
                except ValueError:
                    pass

            # Badge de desconto
            badge_el = card.select_one(".a-badge-text")
            badge = badge_el.get_text().strip() if badge_el else None

            url_produto = f"https://www.amazon.com.br/dp/{asin}"

            produtos.append({
                "asin": asin,
                "nome": nome[:80],
                "preco": preco,
                "preco_original": preco_original,
                "badge": badge,
                "url": url_produto,
            })

        except Exception:
            continue

    return produtos


def varrer_categoria(categoria):
    """Varre múltiplas páginas de uma categoria e retorna todos os produtos"""
    todos_produtos = []
    url_base = categoria["url"]

    log(f"  Varrendo: {categoria['nome']}")

    for pagina in range(1, PAGINAS_VARRER + 1):
        url = f"{url_base}&page={pagina}"
        try:
            pausa = random.uniform(3, 8)
            time.sleep(pausa)

            r = requests.get(url, headers=headers_aleatorios(), timeout=15)

            if r.status_code == 503 or "captcha" in r.text.lower():
                log(f"  ⚠️  Bloqueio na pág {pagina}. Pausando 3 min...")
                time.sleep(180)
                break

            produtos = extrair_produtos_da_pagina(r.text)
            if not produtos:
                log(f"  Página {pagina}: sem produtos. Parando.")
                break

            todos_produtos.extend(produtos)
            log(f"  Página {pagina}: {len(produtos)} produtos encontrados")

        except Exception as e:
            log(f"  Erro na página {pagina}: {e}")
            break

    return todos_produtos


def analisar_e_alertar(produtos, historico):
    """Compara preços com histórico e dispara alertas"""
    alertas_promocao = []
    alertas_queda    = []

    for p in produtos:
        asin = p["asin"]
        preco_atual = p["preco"]
        hist = historico.get(asin)

        # Salva no histórico
        if hist is None:
            # Produto novo — apenas registra
            historico[asin] = {
                "nome": p["nome"],
                "preco_maximo": preco_atual,
                "preco_minimo": preco_atual,
                "preco_anterior": preco_atual,
                "preco_atual": preco_atual,
                "url": p["url"],
                "primeira_vez": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "atualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
            }
            continue

        preco_anterior = hist.get("preco_atual", preco_atual)
        preco_maximo   = hist.get("preco_maximo", preco_atual)

        # Atualiza histórico
        historico[asin].update({
            "nome": p["nome"],
            "preco_anterior": preco_anterior,
            "preco_atual": preco_atual,
            "preco_minimo": min(hist.get("preco_minimo", preco_atual), preco_atual),
            "preco_maximo": max(preco_maximo, preco_atual),
            "url": p["url"],
            "atualizado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })

        if preco_atual >= preco_anterior:
            continue

        # Calcula desconto em relação ao preço máximo registrado
        if preco_maximo > 0:
            desconto_pct = round(((preco_maximo - preco_atual) / preco_maximo) * 100)
        else:
            desconto_pct = 0

        queda_atual = round(((preco_anterior - preco_atual) / preco_anterior) * 100)

        if desconto_pct >= DESCONTO_MINIMO:
            alertas_promocao.append({
                **p,
                "preco_anterior": preco_anterior,
                "preco_maximo": preco_maximo,
                "desconto_pct": desconto_pct,
                "queda_atual": queda_atual,
            })
        elif queda_atual >= 5:
            alertas_queda.append({
                **p,
                "preco_anterior": preco_anterior,
                "queda_atual": queda_atual,
            })

    return alertas_promocao, alertas_queda


def enviar_alertas(alertas_promocao, alertas_queda):
    # Alertas de promoção — um por mensagem
    for a in alertas_promocao[:10]:  # máx 10 por rodada
        msg = (
            f"🔥 <b>PROMOÇÃO DETECTADA!</b>\n\n"
            f"🎵 <b>{a['nome']}</b>\n\n"
            f"📈 Máximo histórico: <s>R$ {a['preco_maximo']:.2f}</s>\n"
            f"💸 Antes: R$ {a['preco_anterior']:.2f}\n"
            f"✅ Agora: <b>R$ {a['preco_atual']:.2f}</b>\n"
            f"📉 <b>{a['desconto_pct']}% abaixo do máximo!</b>\n"
            f"{f'🏷️ Badge: {a[chr(98)+chr(97)+chr(100)+chr(103)+chr(101)]}' if a.get('badge') else ''}\n\n"
            f"🛒 <a href=\"{a['url']}\">Ver na Amazon →</a>\n\n"
            f"<i>VinilOFF · {datetime.now().strftime('%d/%m %H:%M')}</i>"
        )
        enviar_telegram(msg)
        time.sleep(1)

    # Resumo de quedas menores
    if alertas_queda:
        linhas = "\n".join([
            f"📀 {q['nome'][:40]}...\n   R$ {q['preco_anterior']:.2f} → R$ {q['preco_atual']:.2f} (↓{q['queda_atual']}%)"
            for q in alertas_queda[:8]
        ])
        msg = (
            f"📉 <b>Quedas de preço detectadas:</b>\n\n"
            f"{linhas}\n\n"
            f"<i>Abaixo do critério de {DESCONTO_MINIMO}%, mas vale conferir!</i>"
        )
        enviar_telegram(msg)


def varredura_completa():
    log("━" * 50)
    log("🔍 Iniciando varredura completa...")

    historico = carregar_historico()
    todos_produtos = []

    for categoria in CATEGORIAS:
        produtos = varrer_categoria(categoria)
        todos_produtos.extend(produtos)
        time.sleep(random.uniform(5, 10))

    # Remove duplicatas por ASIN
    vistos = set()
    unicos = []
    for p in todos_produtos:
        if p["asin"] not in vistos:
            vistos.add(p["asin"])
            unicos.append(p)

    log(f"\n📀 Total de produtos únicos encontrados: {len(unicos)}")

    alertas_promocao, alertas_queda = analisar_e_alertar(unicos, historico)
    salvar_historico(historico)

    log(f"🔥 Promoções: {len(alertas_promocao)} | 📉 Quedas: {len(alertas_queda)}")

    if alertas_promocao or alertas_queda:
        enviar_alertas(alertas_promocao, alertas_queda)
    else:
        log("Nenhuma promoção nova.")

    log(f"Próxima varredura em {INTERVALO_MINUTOS} minutos.")
    log("━" * 50 + "\n")


def main():
    log("🎵 VinilOFF Bot Automático iniciado!")
    log(f"🔍 Varrendo {len(CATEGORIAS)} categorias, {PAGINAS_VARRER} páginas cada")
    log(f"⏱️  Intervalo: {INTERVALO_MINUTOS} minutos")
    log(f"🎯 Alerta quando desconto ≥ {DESCONTO_MINIMO}%\n")

    enviar_telegram(
        f"🎵 <b>VinilOFF Bot Automático ativado!</b>\n\n"
        f"🔍 Varrendo <b>{len(CATEGORIAS)} categorias</b> da Amazon\n"
        f"📀 Descoberta automática de produtos\n"
        f"🎯 Alerta com desconto ≥ <b>{DESCONTO_MINIMO}%</b>\n"
        f"⏱️  A cada <b>{INTERVALO_MINUTOS} minutos</b>\n\n"
        f"Monitoramento ativo! 🔥"
    )

    while True:
        try:
            varredura_completa()
            time.sleep(INTERVALO_MINUTOS * 60)
        except KeyboardInterrupt:
            log("Bot encerrado.")
            enviar_telegram("⏹️ <b>VinilOFF Bot encerrado.</b>")
            break
        except Exception as e:
            log(f"Erro: {e}. Tentando em 15 min...")
            time.sleep(900)


if __name__ == "__main__":
    main()
