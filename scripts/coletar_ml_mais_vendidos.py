#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mais Vendidos do Mercado Livre — coletor automático.

Roda no GitHub Actions junto com os outros. Pega os campeões de venda de cada
categoria pela API oficial e regrava ml_mais_vendidos.json, que a página lê.

COMO A API FUNCIONA (testado em 10/08/2026, direto no navegador do Patrick):
  GET /highlights/MLB/category/<categoria>   -> 401 sem token, funciona com token
  GET /sites/MLB/search                      -> 403 (fechado pro público)
  GET /sites/MLB/categories                  -> 403 (fechado pro público)
Ou seja: precisa de access token. Ele vale 6 HORAS, então todo dia o robô
renova sozinho usando o refresh_token.

⚠️ PEGADINHA IMPORTANTE: o refresh_token do Mercado Livre é de USO ÚNICO.
Cada renovação devolve um novo. Se a gente não guardar o novo, no dia seguinte
a automação morre. Por isso o script grava o novo em 'novo_refresh.txt' e o
workflow salva de volta no cofre de secrets do GitHub.

NUNCA comitar token nenhum: o repositório é público.

Segredos necessários (Settings > Secrets and variables > Actions):
  ML_CLIENT_ID       — App ID do app criado em developers.mercadolivre.com.br
  ML_CLIENT_SECRET   — Secret Key do mesmo app
  ML_REFRESH_TOKEN   — refresh_token obtido na primeira autorização
  GH_PAT_SECRETS     — token pessoal com permissão de escrever secrets
                       (só serve pra guardar o refresh novo)
"""
import json, os, sys, datetime, urllib.request, urllib.parse, urllib.error

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = os.path.join(RAIZ, "ml_mais_vendidos.json")
NOVO_REFRESH = os.path.join(RAIZ, "novo_refresh.txt")
HOJE = datetime.date.today().isoformat()
DRY = "--dry-run" in sys.argv

API = "https://api.mercadolibre.com"
UA = {"User-Agent": "1painerd-site/1.0 (+https://1painerd.github.io)"}

# categorias que interessam pro público do canal
CATEGORIAS = [
    ("MLB1132", "Brinquedos e Hobbies", "🧸"),
    ("MLB1648", "Informática",          "🖥️"),
    ("MLB1000", "Eletrônicos e Áudio",  "🔌"),
    ("MLB1144", "Games",                "🎮"),
]
POR_CATEGORIA = 10


def get(url, token=None):
    h = dict(UA)
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def renovar_token():
    """Troca o refresh_token por um access_token novo (e um refresh novo)."""
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

    # guarda o refresh NOVO — sem isso a automação para amanhã
    if d.get("refresh_token") and not DRY:
        with open(NOVO_REFRESH, "w", encoding="utf-8") as f:
            f.write(d["refresh_token"])
    return d["access_token"]


def https(u):
    return (u or "").replace("http://", "https://").replace("-I.jpg", "-O.jpg")


def detalhes_itens(ids, token):
    """Anúncios normais (type=ITEM): nome, preço, foto e link, 20 por vez."""
    saida = []
    for i in range(0, len(ids), 20):
        lote = ",".join(ids[i:i + 20])
        try:
            r = get(f"{API}/items?ids={lote}", token)
        except Exception as e:
            print(f"    ! falha no lote de itens: {e}")
            continue
        for it in r:
            b = it.get("body") or {}
            if not b.get("id"):
                continue
            saida.append({
                "id": b["id"],
                "nome": b.get("title", ""),
                "preco": b.get("price"),
                "img": https(b.get("thumbnail")),
                "url": b.get("permalink", ""),
            })
    return saida


def detalhes_produtos(ids, token):
    """Produtos de catálogo (type=PRODUCT). Hoje é isso que o ML devolve na
    maioria dos mais vendidos: um produto único com vários vendedores.
    O preço vem do vencedor da caixa de compra (buy box)."""
    saida = []
    for pid in ids:
        try:
            p = get(f"{API}/products/{pid}", token)
        except Exception as e:
            print(f"    ! falha no produto {pid}: {e}")
            continue
        fotos = p.get("pictures") or []
        bb = p.get("buy_box_winner") or {}
        saida.append({
            "id": pid,
            "nome": p.get("name") or bb.get("title") or "",
            "preco": bb.get("price"),
            "img": https((fotos[0] or {}).get("url") if fotos else bb.get("thumbnail")),
            "url": p.get("permalink") or f"https://www.mercadolivre.com.br/p/{pid}",
        })
    return saida


def main():
    faltando = [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN")
                if not os.environ.get(k)]
    if faltando:
        print("Sem credenciais do Mercado Livre (" + ", ".join(faltando) + ").")
        print("Nada foi alterado — a página segue com os dados de antes.")
        return 0

    try:
        token = renovar_token()
        print("  ✓ token renovado (vale 6h)")
    except urllib.error.HTTPError as e:
        print(f"  ! não consegui renovar o token: {e.code} {e.read()[:200]}")
        print("    Se for 400/invalid_grant, o refresh_token venceu — refazer a autorização.")
        return 0   # não quebra o resto do robô

    saida = {"gerado_em": HOJE, "fonte": "API oficial do Mercado Livre", "categorias": []}
    total = 0
    for cid, nome, emoji in CATEGORIAS:
        try:
            hl = get(f"{API}/highlights/MLB/category/{cid}", token)
            conteudo = hl.get("content") or []
            if not conteudo:
                print(f"  ! {nome}: resposta sem 'content' (chaves: {list(hl)[:8]})")
                continue

            # o ML mistura anúncio avulso (ITEM) com produto de catálogo (PRODUCT)
            tipos = {}
            for c in conteudo:
                t = c.get("type") or "?"
                tipos[t] = tipos.get(t, 0) + 1
            print(f"    {nome}: {len(conteudo)} destaques {tipos}")

            topo = conteudo[:POR_CATEGORIA]
            ids_item = [c["id"] for c in topo if c.get("type") == "ITEM" and c.get("id")]
            ids_prod = [c["id"] for c in topo if c.get("type") == "PRODUCT" and c.get("id")]

            achados = {}
            for it in detalhes_itens(ids_item, token) + detalhes_produtos(ids_prod, token):
                achados[it["id"]] = it

            # respeita a ordem do ranking que o ML mandou
            itens = []
            for pos, c in enumerate(topo, 1):
                it = achados.get(c.get("id"))
                if it:
                    it["rank"] = pos
                    itens.append(it)
            saida["categorias"].append({"id": cid, "nome": nome, "emoji": emoji, "itens": itens})
            total += len(itens)
            print(f"  ✓ {nome}: {len(itens)} itens")
        except Exception as e:
            print(f"  ! {nome}: {e}")

    if not total:
        print("Nenhum item coletado — mantendo o arquivo anterior.")
        return 0

    print(f"total: {total} itens")
    if DRY:
        print("(dry-run: nada gravado)")
        return 0

    with open(ARQ, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"\n## Mais Vendidos ML — {HOJE}\n\n")
            for c in saida["categorias"]:
                topo = c["itens"][0]["nome"][:60] if c["itens"] else "—"
                f.write(f"- **{c['nome']}**: {len(c['itens'])} itens · #1: {topo}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
