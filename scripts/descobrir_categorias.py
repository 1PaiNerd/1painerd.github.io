#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descobridor de categorias do Mercado Livre.

Roda sob demanda (botão Run workflow). Não altera nada no site — só imprime
a árvore de categorias pra gente descobrir o ID exato de cada nicho.

POR QUE ISSO EXISTE:
  A busca da API do ML (/sites/MLB/search) é fechada — devolve 403.
  O que funciona com token é o ranking por categoria:
      /highlights/MLB/category/<id>
  Então, pra achar os mais vendidos de "airfryer", a gente não busca a palavra
  "airfryer": a gente acha a CATEGORIA "Fritadeiras" e pega o ranking dela.
  Este script existe pra descobrir esses ids.

Uso no workflow: python scripts/descobrir_categorias.py
"""
import json, os, sys, urllib.request, urllib.parse

API = "https://api.mercadolibre.com"
UA = {"User-Agent": "1painerd-site/1.0 (+https://1painerd.github.io)"}
PROFUNDIDADE = 3          # quantos níveis descer

# de onde começar a descer — as raízes que interessam pro público do canal
RAIZES = [
    ("MLB5726", "Eletrodomésticos"),
    ("MLB1574", "Casa, Móveis e Decoração"),
    ("MLB1384", "Bebês"),
    ("MLB1246", "Beleza e Cuidado Pessoal"),
    ("MLB1132", "Brinquedos e Hobbies"),
    ("MLB1276", "Esportes e Fitness"),
]

# palavras que interessam: o script marca com ⭐ toda categoria que casa
ALVOS = [
    "fritadeira", "air fry", "processador", "liquidificador", "sanduicheira",
    "grill", "panela", "arroz", "pote", "hermétic", "organizador", "geladeira",
    "utensílio", "silicone", "tábua", "corte", "abridor", "balança", "térmic",
    "garrafa", "mop", "esfregão", "aspirador", "vertical", "tempero", "sapateira",
    "luminária", "led", "sensor", "difusor", "aroma", "manta", "microfibra",
    "cobertor", "pano", "varal", "projetor", "estrela", "copo", "canudo",
    "tapete", "eva", "atividade", "babá", "câmera", "massinha", "slime",
    "escova", "secador", "massageador", "cabeceira", "abajur",
]


def get(url, token):
    req = urllib.request.Request(url, headers={**UA, "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def renovar_token():
    dados = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": os.environ["ML_CLIENT_ID"],
        "client_secret": os.environ["ML_CLIENT_SECRET"],
        "refresh_token": os.environ["ML_REFRESH_TOKEN"],
    }).encode()
    req = urllib.request.Request(
        API + "/oauth/token", data=dados,
        headers={**UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode("utf-8"))
    # ATENÇÃO: este script NÃO grava o refresh novo. Ele é de uso manual e
    # roda sozinho; quem cuida do rodízio é o coletor principal.
    return d["access_token"], d.get("refresh_token")


def interessa(nome):
    n = nome.lower()
    return any(a in n for a in ALVOS)


def descer(cid, nome, token, nivel, linhas):
    marca = " ⭐" if interessa(nome) else ""
    linhas.append(f"{'    '*nivel}{cid}  {nome}{marca}")
    if nivel >= PROFUNDIDADE:
        return
    try:
        c = get(f"{API}/categories/{cid}", token)
    except Exception as e:
        linhas.append(f"{'    '*(nivel+1)}! não consegui abrir ({e})")
        return
    for f in (c.get("children_categories") or []):
        descer(f["id"], f["name"], token, nivel + 1, linhas)


def main():
    faltando = [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN")
                if not os.environ.get(k)]
    if faltando:
        print("Sem credenciais (" + ", ".join(faltando) + ")")
        return 1

    token, novo = renovar_token()
    print("✓ token renovado")
    if novo:
        # o refresh é de uso único: devolve o novo pro workflow guardar
        with open("novo_refresh.txt", "w", encoding="utf-8") as f:
            f.write(novo)

    linhas = []
    for cid, nome in RAIZES:
        linhas.append("")
        linhas.append(f"=== {nome} ===")
        descer(cid, nome, token, 0, linhas)

    texto = "\n".join(linhas)
    print(texto)

    estrelas = [l.strip() for l in linhas if l.endswith("⭐")]
    print(f"\n\n>>> {len(estrelas)} categorias casaram com os alvos:")
    for e in estrelas:
        print("  " + e)

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write("\n## Categorias que casaram com os alvos\n\n```\n")
            f.write("\n".join(estrelas) + "\n```\n")
            f.write("\n<details><summary>árvore completa</summary>\n\n```\n")
            f.write(texto + "\n```\n</details>\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
