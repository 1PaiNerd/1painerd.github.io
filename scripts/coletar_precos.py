#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar de Preços — coletor diário do 1PaiNerd.

Roda dentro do GitHub Actions (de graça, sem PC ligado).
Lê precos.json, coleta o preço de hoje de cada produto, acrescenta um ponto
no histórico e detecta quem bateu o menor preço do período.

FONTES (a ordem importa — usa a primeira que estiver configurada por produto):
  1. mercadolivre  → API oficial do Mercado Livre (grátis, precisa de token no repositório)
  2. amazon        → API oficial de afiliados da Amazon (liberada após 3 vendas qualificadas)
  3. manual        → lê precos_manuais.csv (id,preco) — sempre funciona, é a rede de segurança

IMPORTANTE: NÃO raspa a página da Amazon. A Amazon bloqueia robôs por robots.txt
e raspar coloca a conta de afiliado do Patrick em risco — que é justamente o
negócio que essa ferramenta existe pra alimentar. Só fonte oficial ou manual.

Uso:
    python scripts/coletar_precos.py                # coleta e grava
    python scripts/coletar_precos.py --dry-run      # só mostra o que faria
"""
import json, os, sys, csv, datetime, urllib.request, urllib.error

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ_PRECOS = os.path.join(RAIZ, "precos.json")
ARQ_MANUAL = os.path.join(RAIZ, "precos_manuais.csv")
ARQ_ALERTAS = os.path.join(RAIZ, "alertas.json")
HOJE = datetime.date.today().isoformat()
DRY = "--dry-run" in sys.argv

ML_TOKEN = os.environ.get("ML_ACCESS_TOKEN", "").strip()


def http_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "1painerd-radar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- coletores
def coletar_mercadolivre(prod):
    """API oficial do ML. Precisa do secret ML_ACCESS_TOKEN no repositório."""
    mlb = prod.get("mlb")
    if not mlb or not ML_TOKEN:
        return None
    try:
        d = http_json(f"https://api.mercadolibre.com/items/{mlb}",
                      headers={"Authorization": f"Bearer {ML_TOKEN}",
                               "User-Agent": "1painerd-radar/1.0"})
        p = d.get("price")
        return round(float(p), 2) if p else None
    except Exception as e:
        print(f"  ! ML falhou em {mlb}: {e}")
        return None


def coletar_amazon(prod):
    """
    API oficial de afiliados da Amazon (Creators API, sucessora da PA-API 5).
    Só funciona depois que a conta tiver as vendas qualificadas e as chaves
    estiverem nos secrets. Enquanto não tiver, devolve None e cai pro manual.
    """
    if not os.environ.get("AMZ_ACCESS_KEY"):
        return None
    # TODO: preencher quando as chaves saírem — assinatura AWS SigV4 + GetItems.
    return None


def coletar_manual(prod, tabela):
    v = tabela.get(prod["id"])
    if v is None:
        return None
    try:
        return round(float(str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()), 2)
    except ValueError:
        return None


def ler_manuais():
    if not os.path.exists(ARQ_MANUAL):
        return {}
    with open(ARQ_MANUAL, encoding="utf-8-sig") as f:
        return {r["id"].strip(): r["preco"] for r in csv.DictReader(f) if r.get("id")}


# ---------------------------------------------------------------- principal
def main():
    with open(ARQ_PRECOS, encoding="utf-8") as f:
        dados = json.load(f)

    manuais = ler_manuais()
    novos, falhas, alertas = 0, [], []

    for prod in dados["produtos"]:
        hist = prod.setdefault("historico", [])

        if hist and hist[-1]["d"] == HOJE:
            continue  # já coletado hoje

        preco = (coletar_mercadolivre(prod)
                 or coletar_amazon(prod)
                 or coletar_manual(prod, manuais))

        if preco is None:
            falhas.append(prod["nome"])
            continue

        anteriores = [h["p"] for h in hist]
        hist.append({"d": HOJE, "p": preco})
        novos += 1

        # bateu o menor preço já registrado? (com pelo menos 7 dias de base)
        if len(anteriores) >= 7 and preco < min(anteriores):
            alertas.append({
                "id": prod["id"], "nome": prod["nome"], "preco": preco,
                "minimo_anterior": min(anteriores),
                "queda": round(min(anteriores) - preco, 2),
                "url": prod.get("url", ""), "data": HOJE,
            })

    # a primeira coleta real tira o site do modo exemplo
    if novos and dados.get("modo") == "exemplo":
        print("  * primeira coleta real — saindo do modo exemplo")
        dados["modo"] = "real"
        # joga fora todo o histórico simulado; fica só o que foi lido de verdade hoje
        for prod in dados["produtos"]:
            prod["historico"] = [h for h in prod["historico"] if h["d"] == HOJE]
        # a página ignora produto com histórico vazio, então ninguém aparece com dado falso

    dados["gerado_em"] = HOJE

    # guarda no máximo 400 dias por produto (mantém o arquivo leve)
    for prod in dados["produtos"]:
        prod["historico"] = prod["historico"][-400:]

    print(f"coletados: {novos} | falharam: {len(falhas)} | alertas: {len(alertas)}")
    for n in falhas[:10]:
        print(f"  - sem preço: {n}")

    if DRY:
        print("(dry-run: nada gravado)")
        return 0

    with open(ARQ_PRECOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    with open(ARQ_ALERTAS, "w", encoding="utf-8") as f:
        json.dump({"data": HOJE, "alertas": alertas}, f, ensure_ascii=False, indent=1)

    # resumo que aparece bonito na aba Actions do GitHub
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"## Radar de Preços — {HOJE}\n\n")
            f.write(f"- coletados: **{novos}**\n- falharam: **{len(falhas)}**\n\n")
            if alertas:
                f.write("### 🟢 Bateram o menor preço\n\n")
                for a in alertas:
                    f.write(f"- **{a['nome']}** — R$ {a['preco']:.2f} "
                            f"(caiu R$ {a['queda']:.2f}) · [link]({a['url']})\n")

    # arquivo que o passo seguinte usa pra abrir a issue de alerta
    with open(os.path.join(RAIZ, "alerta_titulo.txt"), "w", encoding="utf-8") as f:
        f.write(f"🟢 {len(alertas)} achadinho(s) no menor preço — {HOJE}" if alertas else "")

    return 0


if __name__ == "__main__":
    sys.exit(main())
