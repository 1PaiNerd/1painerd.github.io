#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descobridor de categorias do Mercado Livre — pelos 30 candidatos do briefing.

POR QUE ISSO EXISTE:
  A busca da API do ML (/sites/MLB/search) é fechada — devolve 403.
  O que funciona é o ranking POR CATEGORIA:
      /highlights/MLB/category/<id>
  Então, pra achar os mais vendidos de "airfryer", a gente precisa do id da
  categoria "Fritadeiras". Este script descobre esse id.

COMO ELE DESCOBRE:
  Usa o /sites/MLB/domain_discovery/search — o mesmo motor que o ML usa pra
  adivinhar a categoria quando um vendedor digita o título do anúncio.
  Uma chamada por produto, em vez de varrer a árvore toda.

Uso: python scripts/descobrir_categorias.py
"""
import json, os, sys, urllib.request, urllib.parse

API = "https://api.mercadolibre.com"
UA = {"User-Agent": "1painerd-site/1.0 (+https://1painerd.github.io)"}

# Os 30 candidatos do briefing de audiência (ago/2026).
# (grupo, nome que o Patrick usou, termo de busca do jeito que um vendedor escreveria)
CANDIDATOS = [
    # ---- rodada 2 (ago/2026): mirando quem realmente segue o canal —
    # mulheres 35-64 são 64% da base. Critério: preço-impulso R$20-150,
    # sem numeração, e de preferência algo que RENDE VÍDEO (dá pra mostrar
    # funcionando em 15 segundos).
    ("Cuidado", "Massageador de pescoço",        "massageador eletrico de pescoco e ombros"),
    ("Cuidado", "Massageador de pés",            "massageador de pes eletrico relaxante"),
    ("Cuidado", "Secador de cabelo",             "secador de cabelo profissional"),
    ("Cuidado", "Prancha alisadora",             "prancha alisadora de cabelo ceramica"),
    ("Cuidado", "Modelador de cachos",           "modelador de cachos babyliss"),
    ("Cuidado", "Depilador elétrico",            "depilador eletrico feminino recarregavel"),
    ("Cuidado", "Lixa elétrica de unha",         "kit manicure eletrico lixa de unha"),
    ("Cuidado", "Escova de dente elétrica",      "escova de dente eletrica recarregavel"),
    ("Cuidado", "Balança corporal digital",      "balanca digital corporal bioimpedancia"),
    ("Cuidado", "Espelho com luz LED",           "espelho de maquiagem com luz led aumento"),
    ("Cuidado", "Bolsa térmica",                 "bolsa termica gel quente e frio"),

    ("Casa",    "Removedor de bolinhas",         "removedor de bolinhas de roupa eletrico"),
    ("Casa",    "Vaporizador de roupas",         "vaporizador de roupas portatil a vapor"),
    ("Casa",    "Ferro de passar",               "ferro de passar roupa a vapor"),
    ("Casa",    "Aspirador de mesa",             "mini aspirador de po portatil de mesa"),
    ("Casa",    "Escova elétrica de limpeza",    "escova eletrica de limpeza multiuso"),
    ("Casa",    "Rodo mágico",                   "rodo magico limpa vidro silicone"),
    ("Casa",    "Cabides de veludo",             "kit cabides de veludo antiderrapante"),
    ("Casa",    "Organizador de gaveta",         "organizador de gaveta colmeia divisoria"),
    ("Casa",    "Umidificador de ar",            "umidificador de ar ultrassonico ambiente"),
    ("Casa",    "Ventilador portátil",           "mini ventilador portatil recarregavel"),
    ("Casa",    "Tapete de banheiro",            "tapete de banheiro antiderrapante secagem"),
    ("Casa",    "Porta-joias / organizador",     "porta joias organizador de bijuterias"),

    ("Cozinha", "Panela de pressão elétrica",    "panela de pressao eletrica"),
    ("Cozinha", "Mixer / batedor",               "mixer eletrico de mao batedor"),
    ("Cozinha", "Cafeteira",                     "cafeteira eletrica"),
    ("Cozinha", "Moedor de café",                "moedor de cafe eletrico"),
    ("Cozinha", "Copo térmico",                  "copo termico inox com tampa"),
    ("Cozinha", "Marmita térmica",               "marmita termica com divisorias"),
    ("Cozinha", "Formas de silicone",            "kit formas de silicone para assar"),
    ("Cozinha", "Escorredor de louça",           "escorredor de louca de pia"),
    ("Cozinha", "Descascador / ralador",         "kit ralador e descascador multiuso"),
    ("Cozinha", "Jarra filtrante",               "jarra filtrante de agua com filtro"),
    ("Cozinha", "Seladora de sacos",             "seladora de embalagens seladora a vacuo"),
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
    return d["access_token"], d.get("refresh_token")


def adivinhar(termo, token):
    """Pergunta pro ML: 'se eu fosse anunciar isso, em que categoria cairia?'"""
    url = f"{API}/sites/MLB/domain_discovery/search?limit=1&q={urllib.parse.quote(termo)}"
    r = get(url, token)
    if not r:
        return None
    p = r[0]
    return {
        "categoria_id": p.get("category_id"),
        "categoria": p.get("category_name"),
        "dominio": p.get("domain_name"),
    }


def tem_ranking(cid, token):
    """Confere se essa categoria realmente devolve ranking de mais vendidos."""
    try:
        hl = get(f"{API}/highlights/MLB/category/{cid}", token)
        return len(hl.get("content") or [])
    except Exception:
        return 0


def main():
    faltando = [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN")
                if not os.environ.get(k)]
    if faltando:
        print("Sem credenciais (" + ", ".join(faltando) + ")")
        return 1

    token, novo = renovar_token()
    print("✓ token renovado")
    if novo:
        with open("novo_refresh.txt", "w", encoding="utf-8") as f:
            f.write(novo)

    achados, perdidos = [], []
    for grupo, nome, termo in CANDIDATOS:
        try:
            r = adivinhar(termo, token)
        except Exception as e:
            print(f"  ! {nome}: {e}")
            perdidos.append((grupo, nome, str(e)))
            continue
        if not r or not r.get("categoria_id"):
            print(f"  ? {nome}: o ML não soube dizer")
            perdidos.append((grupo, nome, "sem palpite"))
            continue
        n = tem_ranking(r["categoria_id"], token)
        marca = "✓" if n else "✗ sem ranking"
        print(f"  {marca} {nome} -> {r['categoria_id']}  {r['categoria']}  ({n} no ranking)")
        achados.append((grupo, nome, r["categoria_id"], r["categoria"], n))

    print(f"\n{len(achados)} de {len(CANDIDATOS)} com categoria")
    com_ranking = [a for a in achados if a[4]]
    print(f"{len(com_ranking)} têm ranking de mais vendidos (é com esses que dá pra trabalhar)")

    # bloco pronto pra colar no coletor
    print("\n--- pra colar no coletor ---")
    for grupo, nome, cid, cat, n in com_ranking:
        print(f'    ("{cid}", "{cat}", "{grupo}"),   # {nome} — {n} no ranking')

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write("\n## Categoria de cada candidato\n\n")
            f.write("| Produto | Categoria do ML | ID | No ranking |\n|---|---|---|---|\n")
            for grupo, nome, cid, cat, n in achados:
                f.write(f"| {nome} | {cat} | `{cid}` | {n or '—'} |\n")
            if perdidos:
                f.write("\n**Não achou:** " + ", ".join(p[1] for p in perdidos) + "\n")
            f.write("\n### Pronto pra colar no coletor\n\n```python\n")
            for grupo, nome, cid, cat, n in com_ranking:
                f.write(f'    ("{cid}", "{cat}", "{grupo}"),   # {nome}\n')
            f.write("```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
