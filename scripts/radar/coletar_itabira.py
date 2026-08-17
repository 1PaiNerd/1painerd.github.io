#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coletar_itabira.py — Radar Político da Fábrica (WFactory / 1PaiNerd Studios)

Puxa dados públicos da Câmara Municipal de Itabira/MG e grava JSON limpo
pro site ler. Roda no GitHub Actions (o sandbox da Fábrica não alcança a API).

FONTE (pública, sem chave):
  https://dadosabertos-portalfacil.azurewebsites.net/api/<entidade>
  Fornecedor "Portal Fácil" (Actcon). idCliente=46 é Itabira, divulgado pela
  própria Câmara em: https://www.itabira.cam.mg.gov.br/dados-abertos

REGRAS DA CASA (não quebrar):
  1. Número sempre anda em par com o que o qualifica (apresentado × aprovado).
  2. Nada de nota composta. O site ordena por coluna de fato; quem julga é
     quem lê.
  3. Nome não reconciliado NÃO vira zero publicado — vira "não sei ainda".
     Mostrar 0 projeto pra quem trabalhou é caluniar por bug.
  4. Não republicar dado pessoal desnecessário (CPF, telefone, nascimento).
  5. Toda ficha carrega link pra fonte oficial.
"""

import json, re, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = "https://dadosabertos-portalfacil.azurewebsites.net/api"
ID_CLIENTE = 46
CIDADE = "Itabira"
UF = "MG"
FONTE_HUMANA = "https://www.itabira.cam.mg.gov.br/dados-abertos"
ANOS = [2025, 2026]          # legislatura atual começa em 2025
PAGESIZE = 100
PAUSA = 0.4                  # gentileza com o servidor público

AQUI = Path(__file__).resolve().parent
ARQ_APELIDOS = AQUI / "apelidos_itabira.json"
SAIDA = AQUI / "itabira.json"
SAIDA_PENDENCIAS = AQUI / "itabira_pendencias.txt"

# campos que NÃO republicamos, mesmo vindo na API
CAMPOS_PROIBIDOS = {"descNumCpf", "dtNascimento", "numTelefone", "numCelular",
                    "numPrefTelefone", "numPrefCelular", "numFax", "numPrefFax"}


def chave(s: str) -> str:
    """Normaliza nome pra comparação: sem acento, maiúsculo, sem sufixo."""
    s = (s or "").strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.upper()
    for suf in (" E OUTROS", " E OUTRO"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return re.sub(r"\s+", " ", s).strip()


def busca(entidade: str, **filtros) -> list:
    """Pagina a API até acabar. Devolve lista de registros."""
    tudo, pagina = [], 1
    while pagina <= 60:
        q = {"idCliente": ID_CLIENTE, "type": "json",
             "page": pagina, "pagesize": PAGESIZE}
        q.update({k: v for k, v in filtros.items() if v is not None})
        url = f"{BASE}/{entidade}?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(
            url, headers={"User-Agent": "RadarPolitico/1.0 (+1painerd.com.br)"})
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                dados = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  ! erro em {entidade} pág {pagina}: {e}", file=sys.stderr)
            break
        if not isinstance(dados, list) or not dados:
            break
        tudo.extend(dados)
        if len(dados) < PAGESIZE:
            break
        pagina += 1
        time.sleep(PAUSA)
    return tudo


def carrega_apelidos() -> dict:
    if not ARQ_APELIDOS.exists():
        return {"confirmados": {}, "nao_sao_vereadores": []}
    return json.loads(ARQ_APELIDOS.read_text(encoding="utf-8"))


def aprovada(materia: dict) -> bool:
    return any(re.search(r"aprovad", (t.get("descStatus") or ""), re.I)
               for t in (materia.get("tramitacao") or []))


def main():
    apelidos = carrega_apelidos()
    confirmados = {chave(k): chave(v) for k, v in
                   (apelidos.get("confirmados") or {}).items()}
    nao_vereador = {chave(x) for x in (apelidos.get("nao_sao_vereadores") or [])}
    lixo = {chave(x["valor"]) for x in
            (apelidos.get("registros_defeituosos_do_cadastro") or [])}

    print(f"→ Câmara de {CIDADE}/{UF}")
    parlamentares = busca("proclegislativosparlamentar")
    print(f"  {len(parlamentares)} registros de parlamentar")

    materias = []
    for ano in ANOS:
        m = busca("proclegislativosmaterialegislativa", numAno=ano)
        print(f"  {len(m)} matérias em {ano}")
        materias.extend(m)

    # --- vereadores da legislatura atual (2025–2028) ---
    vereadores = {}
    for p in parlamentares:
        nome = (p.get("descCompleto") or p.get("descNome") or "").strip()
        k = chave(nome)
        if not k or k in lixo:
            continue
        mandatos = p.get("mandato") or []
        atual = any("2028" in (m.get("dtFimMandato") or "") for m in mandatos)
        if not atual:
            continue
        partidos = p.get("partido") or []
        vereadores[k] = {
            "nome": nome,
            "partido": (partidos[-1].get("descSiglaPartido") if partidos else ""),
            "mandatos": len(mandatos),
            "email": p.get("descEmail") or "",
            "instagram": p.get("descInstagram") or "",
            # contadores sempre em par
            "projetos_lei": 0, "projetos_lei_aprovados": 0,
            "indicacoes": 0, "requerimentos": 0,
            "projetos_resolucao": 0, "total": 0,
            "reconciliado": True,
        }
    print(f"  {len(vereadores)} vereadores na legislatura 2025–2028")

    # --- contagem por autoria ---
    orfaos = {}
    for m in materias:
        tipo = m.get("descTipo") or ""
        for a in (m.get("autoria") or []):
            k = chave(a.get("descAutor") or "")
            if not k or k in nao_vereador:
                continue
            k = confirmados.get(k, k)
            if k not in vereadores:
                orfaos[k] = orfaos.get(k, 0) + 1
                continue
            v = vereadores[k]
            v["total"] += 1
            if re.search(r"projeto de lei", tipo, re.I):
                v["projetos_lei"] += 1
                if aprovada(m):
                    v["projetos_lei_aprovados"] += 1
            elif re.search(r"indica", tipo, re.I):
                v["indicacoes"] += 1
            elif re.search(r"requerimento", tipo, re.I):
                v["requerimentos"] += 1
            elif re.search(r"resolu", tipo, re.I):
                v["projetos_resolucao"] += 1

    # --- REGRA 3: quem tem apelido pendente não publica número ---
    pendentes = {chave(x["cadastro"]) for x in (apelidos.get("a_conferir") or [])}
    for k, v in vereadores.items():
        if k in pendentes and v["total"] == 0:
            v["reconciliado"] = False

    # --- pendências pro humano resolver ---
    linhas = ["PENDÊNCIAS DE RECONCILIAÇÃO — conferir em " + FONTE_HUMANA, ""]
    if orfaos:
        linhas.append("Autores que NÃO bateram com nenhum vereador cadastrado:")
        for k, n in sorted(orfaos.items(), key=lambda x: -x[1]):
            linhas.append(f"  {n:>4}x  {k}")
        linhas.append("")
    naozerado = [v["nome"] for v in vereadores.values() if not v["reconciliado"]]
    if naozerado:
        linhas.append("Vereadores com número OMITIDO (apelido não confirmado):")
        linhas += [f"  - {n}" for n in naozerado]
    SAIDA_PENDENCIAS.write_text("\n".join(linhas), encoding="utf-8")
    print(f"  {len(orfaos)} autores órfãos → {SAIDA_PENDENCIAS.name}")

    agora = datetime.now(timezone(timedelta(hours=-3)))
    saida = {
        "_leiame": ("Dados públicos da Câmara de Itabira. Contagem por autoria. "
                    "Número sempre em par (apresentado × aprovado). "
                    "Sem nota, sem ranking editorial: o site ordena, quem julga "
                    "é quem lê. Vereador com 'reconciliado: false' tem o número "
                    "OMITIDO no site — cadastro de nome pendente de conferência."),
        "cidade": CIDADE, "uf": UF,
        "periodo": {"anos": ANOS, "legislatura": "2025-2028"},
        "fonte": {"api": BASE, "idCliente": ID_CLIENTE, "pagina": FONTE_HUMANA},
        "atualizado_em": agora.strftime("%Y-%m-%d %H:%M") + " (Brasília)",
        "totais": {"materias_lidas": len(materias),
                   "vereadores": len(vereadores),
                   "autores_orfaos": len(orfaos)},
        "vereadores": sorted(vereadores.values(),
                             key=lambda v: (-v["projetos_lei"], v["nome"])),
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    print(f"✔ {SAIDA.name} gravado ({len(vereadores)} vereadores)")


if __name__ == "__main__":
    main()
