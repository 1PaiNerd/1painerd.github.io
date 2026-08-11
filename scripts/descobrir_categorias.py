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
    ("Cozinha", "Airfryer 4-5L",                    "airfryer fritadeira eletrica sem oleo 5 litros"),
    ("Cozinha", "Cortador/fatiador de legumes",     "cortador fatiador de legumes multifuncional"),
    ("Cozinha", "Mini processador elétrico",        "mini processador de alimentos eletrico portatil"),
    ("Cozinha", "Sanduicheira-grill",               "sanduicheira grill eletrica"),
    ("Cozinha", "Panela elétrica de arroz",         "panela eletrica de arroz"),
    ("Cozinha", "Kit potes herméticos",             "kit potes hermeticos empilhaveis mantimentos"),
    ("Cozinha", "Organizador de geladeira",         "organizador de geladeira transparente"),
    ("Cozinha", "Kit utensílios de silicone",       "kit utensilios de silicone com suporte"),
    ("Cozinha", "Tábua com escorredor",             "tabua de corte com escorredor"),
    ("Cozinha", "Abridor de potes automático",      "abridor de latas e potes automatico eletrico"),
    ("Cozinha", "Balança digital de cozinha",       "balanca digital de cozinha"),
    ("Cozinha", "Garrafa térmica com display",      "garrafa termica digital display temperatura"),

    ("Casa",    "Mop giratório",                    "mop giratorio balde esfregao"),
    ("Casa",    "Aspirador vertical sem fio",       "aspirador de po vertical sem fio portatil"),
    ("Casa",    "Organizador de temperos",          "organizador giratorio de temperos armario"),
    ("Casa",    "Sapateira / organizador de porta", "organizador de porta sapateira multiuso"),
    ("Casa",    "Luminária LED com sensor",         "luminaria led com sensor de movimento"),
    ("Casa",    "Difusor de aromas",                "difusor de aromas ultrassonico umidificador"),
    ("Casa",    "Manta de microfibra",              "manta cobertor microfibra casal fofinha"),
    ("Casa",    "Kit panos de microfibra",          "kit panos de microfibra multiuso limpeza"),
    ("Casa",    "Varal retrátil de parede",         "varal retratil de parede"),

    ("Crianças","Projetor de estrelas",             "projetor de estrelas quarto infantil galaxia"),
    ("Crianças","Copo infantil com canudo",         "copo infantil com canudo antivazamento"),
    ("Crianças","Tapete de atividades EVA",         "tapete de atividades eva infantil"),
    ("Crianças","Livro de atividades",              "livro de atividades infantil 300 atividades"),
    ("Crianças","Luminária de cabeceira touch",     "luminaria abajur de cabeceira touch"),
    ("Crianças","Babá eletrônica",                  "baba eletronica camera wifi bebe"),
    ("Crianças","Kit massinha / slime",             "kit massinha de modelar slime educativo"),

    ("Cuidado", "Escova secadora elétrica",         "escova secadora eletrica alisadora"),
    ("Cuidado", "Massageador portátil",             "massageador portatil recarregavel muscular"),
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
