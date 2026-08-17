#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testa a lógica do coletor com um molde do dado REAL de Itabira
(mesmos nomes de campo e mesmas armadilhas encontradas na API em 16/08/2026),
sem depender de rede. Roda no sandbox."""

import json, importlib.util
from pathlib import Path

AQUI = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("col", AQUI / "coletar_itabira.py")
col = importlib.util.module_from_spec(spec); spec.loader.exec_module(col)

# ---- molde com as armadilhas reais ----
PARLAMENTARES = [
    {"descCompleto": "Bernardo Rosa", "descNome": "Bernardo",
     "descNumCpf": "12345678900", "dtNascimento": "01/01/1980",
     "descEmail": "bernardo@itabira.cam.mg.gov.br",
     "mandato": [{"dtFimMandato": "31/12/2024 00:00:00"},
                 {"dtFimMandato": "31/12/2028 00:00:00"}],
     "partido": [{"descSiglaPartido": "PSB"}]},
    {"descCompleto": "Heraldo Noronha", "descNome": "Heraldo",   # ← só "HERALDO" na autoria
     "mandato": [{"dtFimMandato": "31/12/2028 00:00:00"}],
     "partido": [{"descSiglaPartido": "REPUBLICANOS"}]},
    {"descCompleto": "Rodrigo Diguerê",                           # acento na autoria
     "mandato": [{"dtFimMandato": "31/12/2028 00:00:00"}],
     "partido": [{"descSiglaPartido": "MDB"}]},
    {"descCompleto": "Fulano Antigo",                             # fora da legislatura
     "mandato": [{"dtFimMandato": "31/12/2020 00:00:00"}],
     "partido": [{"descSiglaPartido": "XXX"}]},
    {"descCompleto": "não",                                       # registro lixo real
     "mandato": [{"dtFimMandato": "31/12/2028 00:00:00"}],
     "partido": [{"descSiglaPartido": "PSB"}]},
]

APROV = {"tramitacao": [{"descStatus": "Matéria Aprovada"}]}
MATERIAS = [
    {"descTipo": "Projeto de Lei", "autoria": [{"descAutor": "Bernardo Rosa"}], **APROV},
    {"descTipo": "Projeto de Lei", "autoria": [{"descAutor": "BERNARDO ROSA E OUTROS"}]},  # sufixo
    {"descTipo": "Indicação",      "autoria": [{"descAutor": "Bernardo Rosa"}]},
    {"descTipo": "Requerimento",   "autoria": [{"descAutor": "RODRIGO DIGUERE"}]},          # sem acento
    {"descTipo": "Indicação",      "autoria": [{"descAutor": "HERALDO"}]},                  # apelido
    {"descTipo": "Projeto de Lei", "autoria": [{"descAutor": "PREFEITO MUNICIPAL"}], **APROV},
    {"descTipo": "Projeto de Lei", "autoria": [{"descAutor": "DULCE CITI"}]},               # órfão
]

col.busca = lambda ent, **f: PARLAMENTARES if "parlamentar" in ent else (
    MATERIAS if f.get("numAno") == 2026 else [])
col.ANOS = [2026]
col.main()

d = json.loads((AQUI / "itabira.json").read_text(encoding="utf-8"))
por = {v["nome"]: v for v in d["vereadores"]}
falhas = []

def ok(cond, msg):
    print(("  ✔ " if cond else "  ✘ ") + msg)
    if not cond: falhas.append(msg)

print("\n--- verificações ---")
ok(len(d["vereadores"]) == 3,
   f"só entram vereadores da legislatura atual, sem o registro lixo 'não' (deu {len(d['vereadores'])}, esperado 3)")
ok("Fulano Antigo" not in por, "vereador de mandato antigo ficou de fora")
ok("não" not in por, "registro defeituoso 'não' foi ignorado")
b = por.get("Bernardo Rosa", {})
ok(b.get("projetos_lei") == 2, f"sufixo 'E OUTROS' contou pro mesmo autor (PL={b.get('projetos_lei')}, esperado 2)")
ok(b.get("projetos_lei_aprovados") == 1, f"aprovado veio em par com apresentado (aprov={b.get('projetos_lei_aprovados')}, esperado 1)")
ok(por.get("Rodrigo Diguerê", {}).get("requerimentos") == 1, "nome sem acento na autoria bateu com o cadastro acentuado")
h = por.get("Heraldo Noronha", {})
ok(h.get("reconciliado") is False, "vereador com apelido pendente foi marcado como NÃO reconciliado (número omitido, não zerado)")
ok(all(c not in json.dumps(d) for c in ["12345678900", "01/01/1980"]),
   "CPF e data de nascimento NÃO foram republicados")
pend = (AQUI / "itabira_pendencias.txt").read_text(encoding="utf-8")
ok("DULCE CITI" in pend, "autor órfão foi reportado no arquivo de pendências")
ok("PREFEITO" not in json.dumps(d.get("vereadores")), "Prefeito não foi contado como vereador")

print("\n" + ("TODOS OS TESTES PASSARAM ✔" if not falhas else f"FALHAS: {falhas}"))
