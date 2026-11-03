#!/usr/bin/env python3
"""
radar.py — procura vagas [Hiring] no Reddit, avisa no WhatsApp e publica a
lista no seu painel do GitHub Pages (docs/vagas.json).

Roda no seu PC de casa. Só biblioteca padrão do Python 3.9+.

  python radar.py --teste        manda uma mensagem de teste no WhatsApp
  python radar.py                fica rodando e publica no GitHub (git push)
  python radar.py --sem-push     roda sem enviar nada ao GitHub
  python radar.py --uma-vez      um ciclo só (para o Agendador de Tarefas)
  python radar.py --historico    na 1ª vez, também avisa os posts já existentes
  python radar.py --arquivo f.xml  testa com um feed salvo, sem internet

Palavras-chave e subreddits ficam em config.json. Segredos ficam em .env.
"""

import argparse
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARQ_VAGAS = RAIZ / "docs" / "vagas.json"
ATOM = "{http://www.w3.org/2005/Atom}"


# ------------------------------------------------------------ configuração --
def carregar_env():
    arq = RAIZ / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


carregar_env()
CFG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
ENV = lambda k: os.environ.get(k, "").strip()
UA = f"python:freela-radar:v1.0 (by /u/{ENV('REDDIT_USUARIO') or 'freela-radar'})"


def agora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ Reddit --
def baixar_feed():
    url = f"https://www.reddit.com/r/{'+'.join(CFG['subreddits'])}/new/.rss?limit=50"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def texto_limpo(fragmento):
    sem_tags = re.sub(r"<[^>]+>", " ", html.unescape(fragmento or ""))
    return re.sub(r"\s+", " ", html.unescape(sem_tags)).strip()


def ler_feed(xml_bytes):
    raiz = ET.fromstring(xml_bytes)
    posts = []
    for e in raiz.iter(f"{ATOM}entry"):
        link = e.find(f"{ATOM}link")
        cat = e.find(f"{ATOM}category")
        autor = e.find(f"{ATOM}author/{ATOM}name")
        posts.append({
            "id": (e.findtext(f"{ATOM}id") or "").strip(),
            "titulo": (e.findtext(f"{ATOM}title") or "").strip(),
            "link": link.get("href") if link is not None else "",
            "sub": cat.get("term") if cat is not None else "",
            "autor": (autor.text or "").strip() if autor is not None else "",
            "publicado": (e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated") or "").strip(),
            "texto": texto_limpo(e.findtext(f"{ATOM}content")),
        })
    return posts


def _tem(termo, alvo):
    termo = termo.lower()
    if re.fullmatch(r"[a-z0-9 ]+", termo):
        return re.search(rf"\b{re.escape(termo)}\b", alvo) is not None
    return termo in alvo


def avaliar(post):
    titulo = post["titulo"].lower()
    corpo = f"{titulo} {post['texto'].lower()}"
    if "hiring" not in titulo or "for hire" in titulo:
        return None
    if any(_tem(x, corpo) for x in CFG["excluir"]):
        return None
    palavras = [p for p in CFG["palavras"] if _tem(p, corpo)]
    if not palavras:
        return None
    golpe = [g for g in CFG["sinais_golpe"] if _tem(g, corpo)]
    valores = re.findall(
        r"(?:\$|usd\s?)\s?\d[\d,.]*(?:\s?k)?(?:\s?(?:/|per)\s?(?:hr|hour|h|month|mo|week|wk))?",
        corpo, flags=re.I)
    return {"palavras": palavras[:8], "golpe": golpe[:4],
            "valores": list(dict.fromkeys(v.strip() for v in valores))[:4]}


# --------------------------------------------------------------- tradução --
def traduzir(texto):
    """Traduz para português pelo endpoint gratuito do Google. None se falhar."""
    if not texto:
        return ""
    q = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "pt", "dt": "t", "q": texto})
    try:
        with urllib.request.urlopen(f"https://translate.googleapis.com/translate_a/single?{q}", timeout=20) as r:
            return "".join(s[0] for s in json.loads(r.read())[0] if s[0])
    except (urllib.error.URLError, TimeoutError, ValueError, IndexError, TypeError) as e:
        log(f"falha ao traduzir: {e}")
        return None


def traduzir_pendentes(vagas, limite=10):
    """Traduz as vagas que ainda não têm tradução; as que falharem ficam para o próximo ciclo."""
    feitas = 0
    for v in vagas:
        if feitas >= limite:
            break
        if "titulo_pt" in v:
            continue
        titulo, texto = traduzir(v["titulo"]), traduzir(v["texto"])
        if titulo is None or texto is None:
            break
        v["titulo_pt"], v["texto_pt"] = titulo, texto
        feitas += 1
    return feitas


# ------------------------------------------------------------------ avisos --
def whatsapp(texto):
    fone, chave = ENV("CALLMEBOT_PHONE"), ENV("CALLMEBOT_APIKEY")
    if not (fone and chave):
        return False
    q = urllib.parse.urlencode({"phone": fone, "text": texto, "apikey": chave})
    try:
        with urllib.request.urlopen(f"https://api.callmebot.com/whatsapp.php?{q}", timeout=30) as r:
            resp = r.read().decode("utf-8", "replace")
        if "error" in resp.lower() and "queued" not in resp.lower():
            log(f"CallMeBot respondeu com erro: {texto_limpo(resp)[:160]}")
            return False
        return True
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"falha ao mandar WhatsApp: {e}")
        return False


def telegram(texto):
    token, chat = ENV("TELEGRAM_TOKEN"), ENV("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    dados = urllib.parse.urlencode({"chat_id": chat, "text": texto,
                                    "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=20)
        return True
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"falha ao mandar Telegram: {e}")
        return False


def avisar(texto):
    ok_w = whatsapp(texto)
    ok_t = telegram(texto)
    if not (ok_w or ok_t):
        print("\n" + texto + "\n" + "-" * 50)


def mensagem(v):
    partes = []
    if v["golpe"]:
        partes.append("⚠️ Cuidado: " + ", ".join(v["golpe"]))
    partes.append(f"*{v['titulo']}*")
    partes.append(f"r/{v['sub']}" + (" · 💵 " + " · ".join(v["valores"]) if v["valores"] else ""))
    partes.append("🔎 " + ", ".join(v["palavras"][:5]))
    if v["texto"]:
        partes.append(v["texto"][:220] + ("…" if len(v["texto"]) > 220 else ""))
    partes.append(v["link"])
    return "\n".join(partes)


# -------------------------------------------------------------------- dados --
def carregar_vagas():
    try:
        return json.loads(ARQ_VAGAS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"atualizado": None, "vagas": []}


def salvar_vagas(dados):
    dados["vagas"] = sorted(dados["vagas"], key=lambda v: (v["encontrado"], v.get("publicado", "")), reverse=True)[:CFG["guardar_ultimas"]]
    ARQ_VAGAS.parent.mkdir(exist_ok=True)
    ARQ_VAGAS.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def publicar(msg):
    def git(*args):
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)
    git("add", "docs/vagas.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    c = git("commit", "-m", msg)
    if c.returncode != 0:
        log("git commit falhou: " + (c.stderr or c.stdout).strip()[:200]); return
    p = git("push")
    log("publicado no GitHub" if p.returncode == 0 else "git push falhou: " + p.stderr.strip()[:200])


# ------------------------------------------------------------------- ciclo --
def ciclo(a):
    xml_bytes = Path(a.arquivo).read_bytes() if a.arquivo else baixar_feed()
    posts = ler_feed(xml_bytes)
    dados = carregar_vagas()
    conhecidas = {v["id"] for v in dados["vagas"]}
    primeira = dados["atualizado"] is None
    novas = []
    for post in reversed(posts):
        if post["id"] in conhecidas:
            continue
        av = avaliar(post)
        if not av:
            continue
        vaga = {**post, **av, "texto": post["texto"][:1500], "encontrado": agora_iso()}
        dados["vagas"].append(vaga)
        novas.append(vaga)

    traduzidas = traduzir_pendentes(dados["vagas"])
    avisaveis = [v for v in novas if CFG["avisar_golpe_no_whatsapp"] or not v["golpe"]]
    if primeira and not a.historico:
        log(f"primeira execução: {len(novas)} vagas guardadas no painel, sem aviso")
    else:
        limite = CFG["max_whatsapp_por_ciclo"]
        for v in avaliaveis_ordenadas(avisaveis)[:limite]:
            avisar(mensagem(v))
            time.sleep(4)
        if len(avisaveis) > limite:
            extra = f"+{len(avisaveis) - limite} vagas novas no painel"
            avisar(extra + (f": {ENV('PAINEL_URL')}" if ENV("PAINEL_URL") else ""))

    ultima = datetime.fromisoformat(dados["atualizado"]) if dados["atualizado"] else None
    batida_vencida = ultima is None or (datetime.now(timezone.utc) - ultima).total_seconds() > CFG["heartbeat_min"] * 60
    if novas or traduzidas or batida_vencida:
        dados["atualizado"] = agora_iso()
        salvar_vagas(dados)
        if a.push:
            publicar(f"radar: {len(novas)} vaga(s) nova(s)" if novas else "radar: ainda vivo")
    return len(posts), len(novas)


def so_traduzir(a):
    """Com o Reddit fora do ar, ao menos traduz e publica as vagas pendentes."""
    dados = carregar_vagas()
    n = traduzir_pendentes(dados["vagas"])
    if n:
        salvar_vagas(dados)
        if a.push:
            publicar(f"radar: {n} tradução(ões)")


def avaliaveis_ordenadas(vagas):
    # mais palavras-chave batendo primeiro; empate: a mais recente
    return sorted(vagas, key=lambda v: (len(v["palavras"]), v["publicado"]), reverse=True)


def main():
    ap = argparse.ArgumentParser(description="Radar de vagas do Reddit")
    ap.add_argument("--teste", action="store_true")
    ap.add_argument("--uma-vez", action="store_true")
    ap.add_argument("--historico", action="store_true")
    ap.add_argument("--sem-push", dest="push", action="store_false")
    ap.add_argument("--arquivo")
    a = ap.parse_args()

    if a.teste:
        if not (ENV("CALLMEBOT_PHONE") and ENV("CALLMEBOT_APIKEY")) and not ENV("TELEGRAM_TOKEN"):
            sys.exit("Preencha CALLMEBOT_PHONE e CALLMEBOT_APIKEY no arquivo .env")
        avisar("✅ Radar de freela ligado. Vou avisar aqui quando aparecer vaga."
               + (f"\nPainel: {ENV('PAINEL_URL')}" if ENV("PAINEL_URL") else ""))
        log("teste enviado")
        return

    espera, ultimo_aviso_bloqueio = CFG["intervalo_seg"], 0
    while True:
        try:
            total, novas = ciclo(a)
            log(f"feed: {total} posts · vagas novas: {novas}")
            espera = CFG["intervalo_seg"]
        except urllib.error.HTTPError as e:
            espera = min(espera * 2, 1800)
            log(f"Reddit respondeu {e.code}; tento de novo em {espera}s")
            if e.code in (403, 429) and time.time() - ultimo_aviso_bloqueio > 6 * 3600:
                avisar(f"⚠️ Radar: o Reddit está recusando os pedidos (erro {e.code}). Vou continuar tentando.")
                ultimo_aviso_bloqueio = time.time()
            so_traduzir(a)
        except (urllib.error.URLError, TimeoutError, ET.ParseError) as e:
            log(f"falha de rede ou feed: {e}")
            so_traduzir(a)
        if a.uma_vez or a.arquivo:
            break
        time.sleep(espera + random.randint(0, 45))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nParado.")
