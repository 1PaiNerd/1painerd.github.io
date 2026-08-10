#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meus Canais — atualiza os vídeos do site sozinho.

Roda no GitHub Actions 1x por dia. Lê o feed público de cada canal do YouTube
(o mesmo RSS que qualquer leitor de feeds usa — sem API, sem chave, sem custo)
e regrava videos.json. A página canais.html só lê esse arquivo.

Se um canal falhar, os vídeos antigos dele são MANTIDOS — nunca fica página vazia.

Uso:
    python scripts/coletar_videos.py
    python scripts/coletar_videos.py --dry-run
"""
import json, os, re, sys, datetime, urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = os.path.join(RAIZ, "videos.json")
HOJE = datetime.date.today().isoformat()
DRY = "--dry-run" in sys.argv
POR_CANAL = 8  # quantos vídeos mostrar de cada canal

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


def tag(txt, nome):
    m = re.search(r"<%s>(.*?)</%s>" % (nome, nome), txt, re.S)
    return m.group(1).strip() if m else ""


def desescapar(s):
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'")):
        s = s.replace(a, b)
    return s


def buscar(channel_id):
    req = urllib.request.Request(
        FEED.format(channel_id),
        headers={"User-Agent": "1painerd-site/1.0 (+https://1painerd.github.io)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        xml = r.read().decode("utf-8", "replace")

    entradas = xml.split("<entry>")[1:]
    videos = []
    for e in entradas[:POR_CANAL]:
        vid = tag(e, "yt:videoId")
        if not vid:
            continue
        videos.append({
            "id": vid,
            "t": desescapar(tag(e, "title")),
            "d": tag(e, "published")[:10],
        })
    return videos


def main():
    with open(ARQ, encoding="utf-8") as f:
        dados = json.load(f)

    ok, falhou = 0, []
    for canal in dados["canais"]:
        cid = canal.get("channelId")
        if not cid:
            falhou.append(canal["nome"] + " (sem channelId)")
            continue
        try:
            vids = buscar(cid)
            if vids:
                canal["videos"] = vids
                ok += 1
                print(f"  ✓ {canal['nome']}: {len(vids)} vídeos "
                      f"(mais recente {vids[0]['d']})")
            else:
                falhou.append(canal["nome"] + " (feed vazio)")
        except Exception as exc:
            # mantém os vídeos que já estavam lá — melhor antigo do que vazio
            falhou.append(f"{canal['nome']} ({exc})")

    dados["gerado_em"] = HOJE

    print(f"canais atualizados: {ok} | falharam: {len(falhou)}")
    for f_ in falhou:
        print(f"  ! {f_}")

    if DRY:
        print("(dry-run: nada gravado)")
        return 0

    with open(ARQ, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"\n## Meus Canais — {HOJE}\n\n")
            for c in dados["canais"]:
                v = c["videos"][0] if c["videos"] else None
                f.write(f"- **{c['nome']}**: {len(c['videos'])} vídeos"
                        + (f" · último: {v['t'][:60]} ({v['d']})" if v else "") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
