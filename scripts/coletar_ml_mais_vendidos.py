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
HIST = os.path.join(RAIZ, "historico_ml.json")
LINKS = os.path.join(RAIZ, "links_afiliados.json")   # o robô SÓ LÊ este arquivo
SEM_LINK = os.path.join(RAIZ, "sem_link_ml.txt")     # lista pronta pro Gerador
DIAS_HISTORICO = 60      # guarda 2 meses por produto — o resto vira ruído
NOVO_REFRESH = os.path.join(RAIZ, "novo_refresh.txt")
HOJE = datetime.date.today().isoformat()
DRY = "--dry-run" in sys.argv

API = "https://api.mercadolibre.com"
UA = {"User-Agent": "1painerd-site/1.0 (+https://1painerd.github.io)"}

# Categorias que interessam pro público do canal.
# O NOME aqui é só um palpite pra emergência: o script pergunta o nome de
# verdade pra API (/categories/<id>) e usa o oficial. Se o id estiver errado,
# a API responde 404 e a categoria é pulada com aviso — sem inventar nada.
CATEGORIAS = [
    # o núcleo nerd, que já estava rodando
    ("MLB1144",  "Games",                      "🎮"),
    ("MLB1648",  "Informática",                "🖥️"),
    ("MLB1000",  "Eletrônicos e Áudio",        "🔌"),
    ("MLB1132",  "Brinquedos e Hobbies",       "🧸"),
    # o que o público feminino do canal mais compra em marketplace
    ("MLB1246",  "Beleza e Cuidado Pessoal",   "💄"),
    ("MLB1430",  "Calçados, Roupas e Bolsas",  "👟"),
    ("MLB1574",  "Casa, Móveis e Decoração",   "🏠"),
    ("MLB5726",  "Eletrodomésticos",           "🍳"),
    ("MLB1276",  "Esportes e Fitness",         "🏋️"),
    ("MLB1384",  "Bebês",                      "🍼"),
]
POR_CATEGORIA = 10

# ---------------------------------------------------------------------------
# "PRA SUA ROTINA" — a seleção feita pro público real do canal
# (85% mulheres, 83% com 35+, núcleo 35-64: mães e avós — dados do Instagram
#  Insights de ago/2026). Cada linha é a categoria-folha EXATA do Mercado Livre,
#  descoberta pelo próprio motor de classificação deles (domain_discovery).
#
# REGRAS QUE O PATRICK DEFINIU E QUE ESTÃO NO CÓDIGO ABAIXO:
#   · preço-impulso: R$20 a R$150
#   · no máximo 4 âncoras acima disso (as caras, que servem de vitrine)
#   · nada que dependa de tamanho/numeração — troca mata conversão
# ---------------------------------------------------------------------------
ROTINA = [
    # (categoria-folha do ML, nome da folha, grupo, o que a gente procura ali)
    ("MLB456045", "Fritadeiras de ar",        "Cozinha",  "airfryer"),
    ("MLB193813", "Cortadores e trituradores","Cozinha",  "cortador de legumes"),
    ("MLB31674",  "Processadores",            "Cozinha",  "mini processador"),
    ("MLB31683",  "Sanduicheiras",            "Cozinha",  "sanduicheira"),
    ("MLB120373", "Panelas de arroz",         "Cozinha",  "panela de arroz"),
    ("MLB244658", "Potes para alimentos",     "Cozinha",  "potes herméticos"),
    ("MLB277460", "Organizadores de armário", "Cozinha",  "organizador de geladeira"),
    ("MLB277448", "Utensílios",               "Cozinha",  "kit de silicone"),
    ("MLB193618", "Tábuas de corte",          "Cozinha",  "tábua com escorredor"),
    ("MLB30220",  "Balanças de cozinha",      "Cozinha",  "balança digital"),
    ("MLB33388",  "Garrafas térmicas",        "Cozinha",  "garrafa com display"),

    ("MLB186655", "Mop",                      "Casa",     "mop giratório"),
    ("MLB4337",   "Aspiradores",              "Casa",     "aspirador vertical"),
    ("MLB186268", "Sapateiras",               "Casa",     "organizador de porta"),
    ("MLB189195", "Luminárias",               "Casa",     "luminária com sensor"),
    ("MLB268503", "Difusores de aroma",       "Casa",     "difusor ultrassônico"),
    ("MLB186334", "Mantas e cobertores",      "Casa",     "manta fofinha"),
    ("MLB269712", "Panos de limpeza",         "Casa",     "kit microfibra"),
    ("MLB73072",  "Varais",                   "Casa",     "varal retrátil"),

    ("MLB1586",   "Luminárias de mesa",       "Crianças", "abajur / projetor de estrelas"),
    ("MLB260545", "Copos de treinamento",     "Crianças", "copo com canudo"),
    ("MLB1393",   "Tapetes de atividades",    "Crianças", "tapete EVA"),
    ("MLB5364",   "Babá eletrônica",          "Crianças", "babá eletrônica"),
    ("MLB271854", "Massinhas de modelar",     "Crianças", "massinha e slime"),

    # Duas categorias saíram daqui porque não são de cuidado pessoal de verdade —
    # as duas viviam empurrando um espremedor Mondial pro topo da aba:
    #   MLB180327 "Elétricos"        (é eletroportátil de cozinha)
    #   MLB264715 "Escovas elétricas" (mistura escova secadora com espremedor)
    # A escova secadora continua aparecendo na aba ampla "Beleza e Cuidado Pessoal".
    # ---- rodada 2 (11/08/2026): categorias descobertas mirando mulheres 35-64,
    # que são 64% da base do canal. Todas confirmadas com ranking pelo
    # descobridor — nenhuma foi chutada.
    ("MLB48666",  "Panelas elétricas",         "Cozinha",  "panela de pressão elétrica"),
    ("MLB263570", "Mixers",                    "Cozinha",  "mixer de mão"),
    ("MLB9188",   "Cafeteiras",                "Cozinha",  "cafeteira"),
    ("MLB456055", "Moedores de café",          "Cozinha",  "moedor elétrico"),
    ("MLB439179", "Copos térmicos",            "Cozinha",  "copo térmico inox"),
    ("MLB436796", "Formas",                    "Cozinha",  "formas de silicone"),
    ("MLB194034", "Escorredores de louça",     "Cozinha",  "escorredor de pia"),
    ("MLB418005", "Descascadores",             "Cozinha",  "descascador e ralador"),
    ("MLB180387", "Filtros de água",           "Cozinha",  "jarra filtrante"),
    ("MLB277404", "Embaladoras a vácuo",       "Cozinha",  "seladora de sacos"),

    ("MLB432230", "Removedores de bolinhas",   "Casa",     "tira-bolinhas elétrico"),
    ("MLB73062",  "Vaporizadores de roupa",    "Casa",     "vaporizador portátil"),
    ("MLB31689",  "Ferros de passar",          "Casa",     "ferro a vapor"),
    ("MLB99946",  "Aspiradores de mão",        "Casa",     "mini aspirador"),
    ("MLB264060", "Escovas de limpeza",        "Casa",     "escova elétrica multiuso"),
    ("MLB186657", "Rodos",                     "Casa",     "rodo mágico"),
    ("MLB186365", "Cabides",                   "Casa",     "cabides de veludo"),
    ("MLB277563", "Organizadores de gaveta",   "Casa",     "colmeia divisória"),
    ("MLB120425", "Umidificadores",            "Casa",     "umidificador de ambiente"),
    ("MLB269769", "Antiderrapantes de banho",  "Casa",     "tapete de banheiro"),
    ("MLB118039", "Caixas organizadoras",      "Casa",     "porta-joias"),

    ("MLB272178", "Massageadores de pescoço",  "Cuidado",  "massageador cervical"),
    ("MLB5412",   "Secadores de cabelo",       "Cuidado",  "secador"),
    ("MLB44085",  "Pranchas de cabelo",        "Cuidado",  "chapinha"),
    ("MLB44076",  "Modeladores de cachos",     "Cuidado",  "babyliss"),
    ("MLB32137",  "Depiladores",               "Cuidado",  "depilador elétrico"),
    ("MLB70608",  "Kit manicure",              "Cuidado",  "lixa elétrica de unha"),
    ("MLB447211", "Escovas de dente elétricas","Cuidado",  "escova de dente recarregável"),
    ("MLB11617",  "Balanças corporais",        "Cuidado",  "balança de bioimpedância"),
    ("MLB431591", "Espelhos de maquiagem",     "Cuidado",  "espelho com LED"),
    ("MLB432586", "Bolsas de gel",             "Cuidado",  "bolsa térmica"),
]
PRECO_MIN, PRECO_MAX = 20, 150
MAX_ANCORAS = 4          # quantos itens caros entram como vitrine
POR_FOLHA = 6            # quantos olhar em cada categoria-folha
POR_GRUPO = 24           # quantos sobrevivem em cada aba


def nome_oficial(cid, token, palpite):
    """Pergunta pro ML como a categoria se chama de verdade."""
    try:
        c = get(f"{API}/categories/{cid}", token)
        return c.get("name") or palpite, True
    except Exception as e:
        print(f"  ! categoria {cid} não confere ({e}) — usando '{palpite}'")
        return palpite, False


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
                # sem permalink o produto vira link morto no site e não dá pra
                # gerar link de afiliado — /MLB-<numero> é rota válida do ML
                "url": b.get("permalink") or
                       "https://produto.mercadolivre.com.br/MLB-" + b["id"][3:],
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

        # o preço nem sempre vem no produto. Quando não vem, a gente pergunta
        # qual anúncio está vencendo a caixa de compra e pega o preço dele.
        preco = bb.get("price")
        if preco is None:
            try:
                r = get(f"{API}/products/{pid}/items?limit=1", token)
                res = r.get("results") or []
                if res:
                    bb = res[0]
                    preco = bb.get("price")
            except Exception as e:
                print(f"    ! sem preço para {pid}: {e}")

        saida.append({
            "id": pid,
            "nome": p.get("name") or bb.get("title") or "",
            "preco": preco,
            "img": https((fotos[0] or {}).get("url") if fotos else bb.get("thumbnail")),
            "url": p.get("permalink") or f"https://www.mercadolivre.com.br/p/{pid}",
        })
    return saida


def coletar_folha(cid, token, quantos):
    """Pega os campeões de venda de uma categoria-folha."""
    hl = get(f"{API}/highlights/MLB/category/{cid}", token)
    topo = (hl.get("content") or [])[:quantos]
    ids_item = [c["id"] for c in topo if c.get("type") == "ITEM" and c.get("id")]
    ids_prod = [c["id"] for c in topo if c.get("type") == "PRODUCT" and c.get("id")]
    achados = {}
    for it in detalhes_itens(ids_item, token) + detalhes_produtos(ids_prod, token):
        achados[it["id"]] = it
    saida = []
    for pos, c in enumerate(topo, 1):
        it = achados.get(c.get("id"))
        if it:
            it["rank"] = pos
            saida.append(it)
    return saida


def conferir_links(saida):
    """O robô nunca escreve em links_afiliados.json — quem gera link é o painel
    de afiliados, na mão. O que ele faz é vigiar: todo produto que entrou hoje
    e ainda não tem link está rendendo ZERO de comissão. Ele lista esses,
    já em blocos de 10 (que é o tanto que o Gerador do ML aguenta por vez)."""
    try:
        with open(LINKS, encoding="utf-8") as f:
            links = json.load(f)
    except Exception as e:
        print(f"  ! não consegui ler {os.path.basename(LINKS)}: {e}")
        print("    (nenhum link foi perdido — o robô não escreve nesse arquivo)")
        links = {}

    vistos, faltando = set(), []
    for c in saida["categorias"]:
        for it in c["itens"]:
            if it["id"] in vistos:
                continue
            vistos.add(it["id"])
            if not links.get(it["id"]) and it.get("url"):
                faltando.append(it)

    com = len(vistos) - len(faltando)
    print(f"\nlinks de afiliado: {com} de {len(vistos)} produtos rendem comissão")

    if faltando:
        with open(SEM_LINK, "w", encoding="utf-8") as f:
            f.write("\n".join(i["url"] for i in faltando) + "\n")
        print(f"  → {len(faltando)} sem link. Lista salva em "
              f"{os.path.basename(SEM_LINK)}")
    elif os.path.exists(SEM_LINK):
        os.remove(SEM_LINK)

    return com, faltando


def montar_rotina(token):
    """Monta as abas 'pra sua rotina' aplicando os filtros do Patrick."""
    grupos, emojis = {}, {"Cozinha": "🍳", "Casa": "🏠", "Crianças": "🧒", "Cuidado": "💆"}
    for cid, folha, grupo, procurando in ROTINA:
        try:
            itens = coletar_folha(cid, token, POR_FOLHA)
        except Exception as e:
            print(f"    ! {folha} ({procurando}): {e}")
            continue
        for it in itens:
            it["de"] = folha          # de qual prateleira veio
        grupos.setdefault(grupo, []).extend(itens)
        print(f"    ✓ {grupo}/{folha}: {len(itens)}")

    saida = []
    for grupo, itens in grupos.items():
        # tira repetido (o mesmo produto pode aparecer em duas folhas)
        vistos, unicos = set(), []
        for it in itens:
            if it["id"] not in vistos:
                vistos.add(it["id"])
                unicos.append(it)

        # a regra do preço-impulso: o miolo é R$20-150
        impulso = [i for i in unicos if i.get("preco") and PRECO_MIN <= i["preco"] <= PRECO_MAX]
        caros   = [i for i in unicos if i.get("preco") and i["preco"] > PRECO_MAX]
        impulso.sort(key=lambda i: i["rank"])
        caros.sort(key=lambda i: i["rank"])

        # âncoras: as caras entram no fim, no máximo 3, só pra dar régua de valor
        escolhidos = impulso[:POR_GRUPO - MAX_ANCORAS] + caros[:MAX_ANCORAS]
        for pos, it in enumerate(escolhidos, 1):
            it["rank"] = pos

        saida.append({"id": "ROTINA_" + grupo, "nome": grupo,
                      "emoji": emojis.get(grupo, "🛒"), "itens": escolhidos})
        print(f"  ✓ {grupo}: {len(escolhidos)} escolhidos "
              f"(de {len(unicos)} vistos · {len(impulso)} no preço-impulso)")
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
    for cid, palpite, emoji in CATEGORIAS:
        nome, conferido = nome_oficial(cid, token, palpite)
        if conferido and nome != palpite:
            print(f"    (nome oficial de {cid}: '{nome}' — o palpite era '{palpite}')")
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
            com_preco = sum(1 for it in itens if it.get("preco"))
            print(f"  ✓ {nome}: {len(itens)} itens ({com_preco} com preço)")
        except Exception as e:
            print(f"  ! {nome}: {e}")

    print("\n--- Pra sua rotina (seleção do público do canal) ---")
    try:
        rotina = montar_rotina(token)
        saida["categorias"].extend(rotina)
        total += sum(len(c["itens"]) for c in rotina)
    except Exception as e:
        print(f"  ! a seleção da rotina falhou inteira: {e}")

    if not total:
        print("Nenhum item coletado — mantendo o arquivo anterior.")
        return 0

    print(f"total: {total} itens")
    if DRY:
        print("(dry-run: nada gravado)")
        return 0

    with open(ARQ, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))

    # ---- histórico de preço: 1 ponto por produto por dia (é isso que vira o gráfico)
    try:
        with open(HIST, encoding="utf-8") as f:
            historico = json.load(f)
    except Exception:
        historico = {}

    novos = 0
    for c in saida["categorias"]:
        for it in c["itens"]:
            if not it.get("preco"):
                continue
            linha = historico.setdefault(it["id"], [])
            if linha and linha[-1].get("d") == HOJE:
                linha[-1]["p"] = it["preco"]      # rodou 2x no mesmo dia: corrige
            else:
                linha.append({"d": HOJE, "p": it["preco"]})
                novos += 1
            del linha[:-DIAS_HISTORICO]

    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, separators=(",", ":"))
    print(f"histórico: {novos} preços novos, {len(historico)} produtos acompanhados")

    com_link, faltando = conferir_links(saida)

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"\n## Mais Vendidos ML — {HOJE}\n\n")
            for c in saida["categorias"]:
                topo = c["itens"][0]["nome"][:60] if c["itens"] else "—"
                f.write(f"- **{c['nome']}**: {len(c['itens'])} itens · #1: {topo}\n")

            n = len(faltando)
            f.write(f"\n### Comissão\n\n{com_link} de {com_link + n} produtos "
                    f"têm link de afiliado.\n")
            if not n:
                f.write("\n**Tudo rendendo comissão hoje.** Nada a fazer.\n")
            else:
                f.write(f"\n**{n} produto(s) sem link — hoje eles dão R$0.**\n\n"
                        "Cola cada bloco no Gerador de links da Central de "
                        "Afiliados (ele aceita 10 por vez):\n")
                for i in range(0, n, 10):
                    f.write(f"\n**Bloco {i // 10 + 1}**\n\n```\n")
                    f.write("\n".join(x["url"] for x in faltando[i:i + 10]))
                    f.write("\n```\n")
                f.write("\nDepois é só somar os links em `links_afiliados.json` "
                        "— o robô nunca mexe nesse arquivo, então nada do que "
                        "já está lá se perde.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
