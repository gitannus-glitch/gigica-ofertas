#!/usr/bin/env python3
"""Confere os dados antes de publicar. Sai com erro se algo estiver errado."""
import json, os, sys

TAG = "tag=gigicaofertas-20"
CATS = ["destaques", "mais-vendidos", "eletronicos", "eletrodomesticos", "beleza",
        "perfumes", "suplementos", "casa-mercado", "livros", "bebidas"]
# padrões que indicariam credencial vazando (montados em partes para não casar com este arquivo)
PROIBIDO = ["amzn" + "1.application-oa2-client.", "amzn" + "1.oa2-cs.v1."]

erros = []
d = json.load(open("ofertas.json", encoding="utf-8"))
json.load(open("historico.json", encoding="utf-8"))
ids = {c["id"]: c for c in d["categorias"]}
for cid in CATS:
    n = len(ids.get(cid, {}).get("itens", []))
    if n < 3:
        erros.append(f"categoria {cid} com {n} itens")
for c in d["categorias"]:
    for i in c["itens"]:
        if TAG not in i.get("link", ""):
            erros.append(f"link sem tag: {i.get('asin')}")
        if not isinstance(i.get("preco"), (int, float)) or i["preco"] <= 0:
            erros.append(f"preço inválido: {i.get('asin')}")

for raiz, dirs, arquivos in os.walk("."):
    dirs[:] = [x for x in dirs if x != ".git"]
    for a in arquivos:
        caminho = os.path.join(raiz, a)
        try:
            txt = open(caminho, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        if any(p in txt for p in PROIBIDO):
            erros.append(f"possível credencial em {caminho}")

if erros:
    print("FALHOU:", *erros[:20], sep="\n- ")
    sys.exit(1)
print("ok:", {c["id"]: len(c["itens"]) for c in d["categorias"]})
