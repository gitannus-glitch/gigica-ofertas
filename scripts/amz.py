#!/usr/bin/env python3
"""Gigica Ofertas — atualização via Amazon Creators API (só biblioteca padrão).

Uso (as chaves ficam nos Secrets do GitHub, NUNCA no código):
  AMZ_CID='...' AMZ_CSEC='...' python3 -I amz.py /caminho/do/repo

Lê ofertas.json/historico.json do repo, consulta a API e reescreve os dois arquivos.
Em erro geral da API (403 AssociateNotEligible etc.) NÃO altera nada e sai com código 2.
Nunca imprime credenciais.
"""
import json, os, sys, time, math, re, hashlib, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone

TAG = "giovannast20-20"            # ID principal (usado nas chamadas da API)
LINK_TAG = "gigicaofertas-20"     # ID de rastreamento do site (vai nos links)
MKT = "www.amazon.com.br"
BASE = "https://creatorsapi.amazon/catalog/v1/"
SP = timezone(timedelta(hours=-3))  # São Paulo (sem horário de verão)
RES = ["itemInfo.title", "itemInfo.byLineInfo", "images.primary.large",
       "offersV2.listings.price", "offersV2.listings.merchantInfo",
       "offersV2.listings.availability", "offersV2.listings.isBuyBoxWinner",
       "offersV2.listings.dealDetails"]

CATS = [
    ("eletronicos", "Eletrônicos", 30, ["smart tv samsung 55", "smart tv lg", "smart tv tcl", "iphone", "galaxy", "notebook",
        "smartwatch", "apple watch", "airpods", "fone jbl", "fone sony", "headset gamer", "caixa de som jbl", "soundbar",
        "kindle", "echo", "fire tv stick", "tablet", "ipad", "playstation 5 console", "xbox", "nintendo switch",
        "monitor", "mouse logitech", "teclado logitech", "ssd", "impressora", "câmera de segurança", "carregador anker"]),
    ("eletrodomesticos", "Eletrodomésticos", 30, ["air fryer", "robô aspirador", "aspirador vertical", "aspirador de pó",
        "cafeteira", "cafeteira espresso", "liquidificador", "micro-ondas", "ventilador", "geladeira", "máquina de lavar",
        "lava e seca", "fogão", "cooktop", "forno elétrico", "purificador de água", "panela elétrica", "batedeira",
        "processador de alimentos", "mixer", "sanduicheira", "chaleira elétrica", "ferro de passar", "ar condicionado"]),
    ("beleza", "Beleza", 25, ["protetor solar", "sérum facial", "la roche-posay", "vichy", "cerave", "kérastase",
        "shampoo profissional", "máscara capilar", "creme hidratante corporal", "maquiagem", "base maybelline",
        "máscara de cílios", "secador de cabelo", "chapinha", "escova secadora"]),
    ("perfumes", "Perfumes", 25, ["perfume importado feminino", "perfume masculino importado", "perfume nacional",
        "perfume carolina herrera", "perfume paco rabanne", "perfume dior", "perfume lancôme", "perfume azzaro",
        "perfume versace", "perfume calvin klein", "perfume natura", "perfume boticário", "body splash",
        "perfume jean paul gaultier", "perfume hugo boss", "perfume yves saint laurent", "perfume prada",
        "perfume antonio banderas", "perfume giorgio armani", "perfume lacoste", "perfume ralph lauren"]),
    ("suplementos", "Suplementos", 25, ["creatina", "whey protein", "whey isolado", "pré-treino", "colágeno",
        "barra de proteína", "multivitamínico", "ômega 3", "glutamina", "bcaa",
        "whey protein concentrado", "proteína vegana", "vitamina d", "vitamina c", "magnésio",
        "hipercalórico", "pasta de amendoim", "coqueteleira"]),
    ("casa-mercado", "Casa & Mercado", 20, ["sabão líquido", "sabão em pó", "amaciante", "desinfetante", "limpador perfumado",
        "detergente", "pastilha lava-louças", "papel higiênico", "papel toalha", "saco de lixo", "shampoo", "condicionador",
        "sabonete", "creme dental", "enxaguante bucal", "desodorante", "aparelho de barbear", "absorvente", "fralda",
        "lenço umedecido", "café", "cápsulas de café", "azeite", "achocolatado"]),
    ("bebidas", "Bebidas", 20, ["whisky", "buchanans", "johnnie walker", "jack daniels", "chivas", "gin", "vodka grey goose",
        "vodka absolut", "tequila", "rum", "aperol", "licor", "vinho tinto", "vinho branco", "espumante", "champagne",
        "cerveja", "cerveja heineken"]),
    ("livros", "Livros", 20, ["livros mais vendidos", "romance", "colleen hoover", "autoajuda", "desenvolvimento pessoal",
        "finanças pessoais livro", "box de livros", "fantasia livro", "suspense livro", "ficção científica livro",
        "biografia", "livro infantil", "mangá", "hq", "livro de receitas", "clássicos da literatura", "bíblia"]),
]
RANK_SALES = ["browseNodeInfo.browseNodes.salesRank"]
# Mais vendidos: tipos de produto (sem bebidas alcoólicas, para a aba não precisar do aviso 18+)
MV_KW = ["air fryer", "smart tv", "fone de ouvido bluetooth", "iphone", "celular samsung", "kindle", "echo dot",
         "robô aspirador", "cafeteira", "liquidificador", "notebook", "smartwatch", "perfume feminino", "perfume masculino",
         "protetor solar", "shampoo", "creatina", "whey protein", "sabão líquido", "papel higiênico", "café"]
MV_POR_KW = 3
ALTO_TICKET = {"eletronicos", "eletrodomesticos"}
DESCARTE = re.compile(r"\b(capa|capinha|case|pel[ií]cula|suporte|cabo|adaptador|compat[ií]vel|para iphone|para galaxy|"
                      r"seminovo|recondicionado|usado|refil|controle remoto universal|skin|adesivo|tampa pl[aá]stica|tampa para|"
                      r"para kindle|smartwatch relógio inteligente|gen[eé]rico)\b", re.I)
ALEGACAO = re.compile(r",?\s*[^,|–-]*\b(fun[cç][aã]o articular|imunidade|emagre\w*|queima\w*|sa[uú]de\w*|auxilia\w*|contribui\w*|"
                      r"melhora\w*|ganho de massa|defini[cç][aã]o|desempenho|disposi[cç][aã]o)\b[^,|]*", re.I)
MAX_POR_CAT = 60
PAGINAS = 2


class ApiErro(Exception):
    pass


# ---------------- HTTP ----------------
_ultimo = [0.0]

def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))

def token():
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": os.environ["AMZ_CID"],
        "client_secret": os.environ["AMZ_CSEC"], "scope": "creatorsapi::default"}).encode()
    try:
        return _post("https://api.amazon.com/auth/o2/token", data,
                     {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]
    except urllib.error.HTTPError as e:
        raise ApiErro(f"token: HTTP {e.code} {e.read()[:300].decode('utf-8','replace')}")

def chamar(tok, endpoint, body):
    for tentativa in range(5):
        espera = 1.5 - (time.time() - _ultimo[0])
        if espera > 0:
            time.sleep(espera)
        _ultimo[0] = time.time()
        try:
            return _post(BASE + endpoint, json.dumps(body).encode(), {
                "Authorization": f"Bearer {tok}", "Content-Type": "application/json", "x-marketplace": MKT})
        except urllib.error.HTTPError as e:
            txt = e.read()[:600].decode("utf-8", "replace")
            if e.code == 429 and tentativa < 4:
                time.sleep(3); continue
            raise ApiErro(f"{endpoint}: HTTP {e.code} {txt}")
        except urllib.error.URLError as e:
            if tentativa < 2:
                time.sleep(3); continue
            raise ApiErro(f"{endpoint}: rede {e.reason}")
    raise ApiErro(f"{endpoint}: 429 persistente")


# ---------------- leitura de item ----------------
def g(o, *ks):
    for k in ks:
        if o is None: return None
        if isinstance(o, dict):
            o = o.get(k, o.get(k[:1].upper() + k[1:]))
        elif isinstance(o, list) and isinstance(k, int):
            o = o[k] if len(o) > k else None
        else:
            return None
    return o

def ler(item):
    asin = g(item, "asin")
    titulo = g(item, "itemInfo", "title", "displayValue")
    marca = g(item, "itemInfo", "byLineInfo", "brand", "displayValue") or g(item, "itemInfo", "byLineInfo", "manufacturer", "displayValue")
    img = g(item, "images", "primary", "large", "url") or g(item, "images", "primary", "medium", "url")
    ls = g(item, "offersV2", "listings") or []
    if not ls: return None
    oferta = next((l for l in ls if g(l, "isBuyBoxWinner")), None) or \
        min(ls, key=lambda l: g(l, "price", "money", "amount") or 9e9)
    preco = g(oferta, "price", "money", "amount")
    if not asin or not titulo or not preco: return None
    era = g(oferta, "price", "savingBasis", "money", "amount")
    pct = g(oferta, "price", "savings", "percentage")
    if pct is None and era and era > preco: pct = round((1 - preco / era) * 100)
    return {"asin": asin, "titulo": titulo, "marca": marca or "", "imagem": img,
            "preco": round(float(preco), 2), "era": round(float(era), 2) if era else None,
            "desconto": int(pct or 0), "selo": g(oferta, "dealDetails", "badge"),
            "fim": g(oferta, "dealDetails", "endTime"), "vendido": g(oferta, "dealDetails", "percentClaimed"),
            "acesso": g(oferta, "dealDetails", "accessType"),
            "vendedor": g(oferta, "merchantInfo", "name") or "",
            "disp": (g(oferta, "availability", "type") or "").upper()}

def vendedor_ok(p):
    if not p["marca"] or p["marca"].lower() in ("genérico", "generico", "generic"):
        return False
    v = p["vendedor"].lower()
    return "amazon" in v or (p["marca"] and p["marca"].lower() in v) or "loja oficial" in v or "oficial" in v

def em_estoque(p):
    return p["disp"] in ("", "IN_STOCK", "NOW", "AVAILABLE") or "STOCK" in p["disp"] and "OUT" not in p["disp"]

# ---------- Variedade ----------
MAX_POR_MARCA = 4
GENERICAS = set("perfume perfumes feminino masculino unissex eau parfum toilette edp edt colonia deo kit com para the and des "
                "de da do das dos em e o a os as um uma sem mais novo nova original".split())

def chave_produto(titulo, marca=""):
    """Mesmo produto em outro tamanho/cor → mesma chave (ex.: La Vie Est Belle 30ml e 100ml)."""
    ws = [w for w in re.findall(r"[a-z0-9]+", sem_acento(titulo)) if len(w) > 2 and w not in GENERICAS and not re.match(r"^\d", w)]
    return (sem_acento(marca or ""), " ".join(ws[:4]))

def dias_no_site(asin, hist):
    return len({x[0][:10] for x in hist.get(asin, [])})

def frescor(asin, hist):
    """Recém-chegado vale mais na ordem; quem está há muitos dias desce."""
    d = dias_no_site(asin, hist)
    return 1.0 if d <= 1 else 0.85 if d == 2 else 0.72 if d <= 4 else 0.6

def sorteio(asin, slot):
    """Embaralhamento leve e estável dentro de cada meia hora (±12%)."""
    h = int(hashlib.md5(f"{asin}|{slot}".encode()).hexdigest()[:6], 16) / 0xFFFFFF
    return 0.88 + 0.24 * h

def ordenar_vitrine(itens, hist, slot):
    return sorted(itens, key=lambda i: -((i.get("desconto") or 0) + 1) * frescor(i["asin"], hist) * sorteio(i["asin"], slot))

def slot_atual(agora):
    return agora.strftime("%Y%m%d") + f"{agora.hour * 2 + agora.minute // 30:02d}"

def stats_hist(asin, preco, hist, limite30):
    serie = [x for x in hist.get(asin, []) if x[0] >= limite30]
    ult = serie[-1][1] if serie else None
    menor30, abaixo = False, None
    if len(serie) >= 6 and len({x[0][:10] for x in serie}) >= 2:
        precos = [x[1] for x in serie]
        media = sum(precos) / len(precos)
        menor30 = preco <= min(precos) and preco < max(precos)
        if media - preco >= max(5, media * 0.05):
            abaixo = int(round(media - preco))
    return {"menor30": menor30, "abaixoMedia": abaixo, "baixou": bool(ult and preco < ult)}

def campos_oferta(p):
    """Dados de tempo da oferta (relâmpago/Black Friday) para o site."""
    out = {}
    if p.get("fim"): out["fim"] = p["fim"]
    if p.get("vendido") is not None: out["vendido"] = int(p["vendido"])
    if p.get("acesso") and "PRIME" in str(p["acesso"]).upper(): out["primeExclusivo"] = True
    return out

RELAMPAGO_HORAS = 30   # entra na aba Relâmpago se a oferta acaba em até 30h (ou tem % resgatado)

def montar_relampago(cats, nomes, agora_utc):
    lim = (agora_utc + timedelta(hours=RELAMPAGO_HORAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    agora_s = agora_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    vistos, out = set(), []
    for cid in DEST_CATS + ["mais-vendidos"]:
        for i in cats.get(cid, []):
            if i["asin"] in vistos or i.get("desconto", 0) <= 0: continue
            fim = i.get("fim")
            if not fim or fim <= agora_s: continue
            if i.get("vendido") is None and fim > lim: continue
            if (i.get("vendido") or 0) >= 100: continue
            vistos.add(i["asin"]); out.append({**i, "categoria": i.get("categoria") or nomes.get(cid, cid)})
    out.sort(key=lambda i: (i["fim"], -(i.get("desconto") or 0)))
    return out[:60]

DEST_CATS = ["eletronicos", "eletrodomesticos", "beleza", "perfumes", "suplementos", "casa-mercado", "livros"]
DEST_TOTAL = 12     # produtos na aba Destaques
DEST_TOPO = 5       # cada categoria contribui com uma das suas 5 melhores ofertas

def nota(i):
    """Desconto x peso do preço (suavizado) x bônus de selo de oferta."""
    return i["desconto"] * math.log10(max(i["preco"], 10)) * (1.3 if i.get("selo") else 1)

def montar_destaques(cats, nomes, hora):
    """12 destaques: o melhor de cada categoria + extras, girando a cada hora entre o top 5 de cada uma.
    A cada atualização (hora diferente) entra outra oferta de ponta, então a vitrine varia ao longo do dia."""
    topo = {}
    for cid in DEST_CATS:
        cand = sorted([i for i in cats.get(cid, []) if not i.get("eraSuspeito") and i.get("desconto", 0) > 0],
                      key=lambda i: -nota(i))[:DEST_TOPO]
        if cand: topo[cid] = [{**i, "categoria": nomes.get(cid, cid)} for i in cand]
    ordem = [c for c in DEST_CATS if c in topo]
    if not ordem: return []
    k = hora % len(ordem)
    ordem = ordem[k:] + ordem[:k]          # a categoria que abre a vitrine também gira
    saida, vistos, rodada = [], set(), 0
    while len(saida) < DEST_TOTAL and rodada < DEST_TOPO:
        for cid in ordem:
            lst = topo[cid]
            i = lst[(hora + rodada) % len(lst)]
            if i["asin"] in vistos: continue
            vistos.add(i["asin"]); saida.append(i)
            if len(saida) >= DEST_TOTAL: break
        rodada += 1
    return saida

def sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")

def nome_curto(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.split(r"\s[|]\s|\s[–-]\s(?=[A-ZÁÉÍÓÚ][a-zà-ú]+ (?:para|de|com|os|a|o)\b)", t)[0].strip()
    if len(t) <= 90: return t
    corte = t[:90]
    return corte[:corte.rfind(" ")].rstrip(",;-–— ") + "…"


# ---------------- main ----------------
def main(repo):
    agora = datetime.now(SP)
    carimbo = agora.strftime("%Y-%m-%d %H:%M")
    of_path, hi_path = os.path.join(repo, "ofertas.json"), os.path.join(repo, "historico.json")
    try: antigo = json.load(open(of_path, encoding="utf-8"))
    except Exception: antigo = {"categorias": []}
    try: hist = json.load(open(hi_path, encoding="utf-8"))
    except Exception: hist = {}

    tok = token()
    res = list(RES)
    ciclo = (agora.timetuple().tm_yday * 24 + agora.hour) // 2
    paginas = [1, 2 + ciclo % 4]          # sempre a 1ª página + uma página mais funda que gira (2ª a 5ª)
    usados, cats_out, log = set(), {}, {}
    chaves_glob = set()

    def busca(kw, minp, recursos_extra=()):
        todos = []
        for pg in paginas:
            try:
                its = busca_pg(kw, minp, pg, None, recursos_extra)
            except ApiErro as e:
                # erro geral (credencial/conta/limite) derruba a execução; erro de uma busca só pula a palavra
                if any(x in str(e) for x in ("HTTP 401", "HTTP 403", "token", "429 persistente", "rede")):
                    raise
                log.setdefault("buscas_puladas", []).append(f"{kw} p{pg}: {str(e)[:80]}")
                break
            todos += its
            if len(its) < 10: break
        return todos

    def busca_pg(kw, minp, pg, extra=None, recursos_extra=()):
        nonlocal res
        body = {"marketplace": MKT, "partnerTag": TAG, "keywords": kw, "itemCount": 10, "itemPage": pg,
                "merchant": "Amazon", "resources": res + list(recursos_extra), "languagesOfPreference": ["pt_BR"]}
        if minp: body["minSavingPercent"] = minp
        if extra: body.update(extra)
        try:
            r = chamar(tok, "searchItems", body)
        except ApiErro as e:
            if "images.primary.large" in str(e) and "images.primary.large" in res:
                res = [x for x in res if x != "images.primary.large"] + ["images.primary.medium"]
                body["resources"] = res + list(recursos_extra)
                try:
                    r = chamar(tok, "searchItems", body)
                except ApiErro as e2:
                    if "images.primary" in str(e2):
                        res = [x for x in res if not x.startswith("images.")]
                        body["resources"] = res + list(recursos_extra)
                        r = chamar(tok, "searchItems", body)
                    else:
                        raise
            else:
                raise
        return g(r, "searchResult", "items") or []

    for cid, cnome, minp, kws in CATS:
        cand = []
        livros = cid == "livros"
        for kw in kws:
            for it in busca(kw, minp, RANK_SALES if livros else ()):
                p = ler(it)
                if not p or not em_estoque(p) or p["desconto"] < minp:
                    continue
                if livros:
                    # livro não tem "marca": exige vendido pela Amazon e descarta usados
                    if "amazon" not in p["vendedor"].lower() or re.search(r"\b(usado|seminovo)\b", p["titulo"], re.I):
                        continue
                    nos = [n for n in (g(it, "browseNodeInfo", "browseNodes") or []) if g(n, "salesRank")]
                    if nos:
                        m = min(nos, key=lambda n: g(n, "salesRank"))
                        if int(g(m, "salesRank")) <= 100 and g(m, "displayName"):
                            p["_rank"] = (int(g(m, "salesRank")), g(m, "displayName"), 0)
                elif not vendedor_ok(p) or DESCARTE.search(p["titulo"]):
                    continue
                p["_kw"] = kw
                cand.append(p)
        vistos, final = set(), []
        chaves = set()
        # novidades primeiro: produtos há vários dias no site perdem prioridade na seleção
        cand.sort(key=lambda p: -(p["desconto"] + 1) * frescor(p["asin"], hist))
        produtos, por_marca = set(), {}
        # diversidade: no máximo 4 por palavra-chave na primeira passada; 1 tamanho por produto; até 4 por marca
        for limite in (4, 99):
            cont = {}
            for p in cand:
                if p["asin"] in vistos or p["asin"] in usados: continue
                ch = (p["marca"].lower() or p["asin"], p["preco"])
                if ch in chaves or ch in chaves_glob: continue
                kp = chave_produto(p["titulo"], p["marca"])
                if kp[1] and kp in produtos: continue
                mk = sem_acento(p["marca"])
                if mk and por_marca.get(mk, 0) >= MAX_POR_MARCA: continue
                if cont.get(p["_kw"], 0) >= limite: continue
                cont[p["_kw"]] = cont.get(p["_kw"], 0) + 1
                produtos.add(kp); por_marca[mk] = por_marca.get(mk, 0) + 1
                vistos.add(p["asin"]); chaves.add(ch); final.append(p)
                if len(final) >= MAX_POR_CAT: break
            if len(final) >= MAX_POR_CAT: break
        usados |= vistos
        chaves_glob |= chaves
        cats_out[cid] = (cnome, final)

    # ---- Mais vendidos: ranking de vendas da Amazon na categoria do produto ----
    mv, mv_vistos, mv_chaves = [], set(), set()
    for ordem, kw in enumerate(MV_KW):
        try:
            its = busca_pg(kw, 0, 1, {"sortBy": "Featured"}, ["browseNodeInfo.browseNodes.salesRank"])
        except ApiErro as e:
            if any(x in str(e) for x in ("HTTP 401", "HTTP 403", "token", "429 persistente", "rede")):
                raise
            log.setdefault("buscas_puladas", []).append(f"mais vendidos {kw}: {str(e)[:80]}")
            continue
        cand = []
        palavras = [w for w in sem_acento(kw).split() if len(w) >= 4]
        for it in its:
            p = ler(it)
            if not p or not vendedor_ok(p) or not em_estoque(p) or DESCARTE.search(p["titulo"]):
                continue
            if not any(w in sem_acento(p["titulo"]) for w in palavras):
                continue
            nos = [n for n in (g(it, "browseNodeInfo", "browseNodes") or []) if g(n, "salesRank")
                   and not re.search(r"livro|hq|mang[aá]|e-?book|graphic", g(n, "displayName") or "", re.I)]
            t = p["titulo"].lower()
            if "masculin" in t: nos = [n for n in nos if "feminin" not in (g(n, "displayName") or "").lower()]
            if "feminin" in t: nos = [n for n in nos if "masculin" not in (g(n, "displayName") or "").lower()]
            if not nos: continue
            melhor = min(nos, key=lambda n: g(n, "salesRank"))
            pos, nome_cat = int(g(melhor, "salesRank")), g(melhor, "displayName") or g(melhor, "contextFreeName") or ""
            if pos > 50 or not nome_cat: continue
            p["_rank"] = (pos, nome_cat, ordem)
            cand.append(p)
        cand.sort(key=lambda p: p["_rank"][0])
        n = 0
        for p in cand:
            ch = (p["marca"].lower(), p["preco"])
            if p["asin"] in mv_vistos or ch in mv_chaves: continue
            mv_vistos.add(p["asin"]); mv_chaves.add(ch); mv.append(p); n += 1
            if n >= MV_POR_KW: break
    mv.sort(key=lambda p: (p["_rank"][0], p["_rank"][2]))

    limite30 = (agora - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")

    def para_json(p, cid):
        if cid == "suplementos":
            p = {**p, "titulo": ALEGACAO.sub("", p["titulo"]).strip(" ,-–")}
        susp = cid in ("eletronicos", "mais-vendidos") and p["desconto"] > 50
        return {**stats_hist(p["asin"], p["preco"], hist, limite30), "asin": p["asin"], "nome": nome_curto(p["titulo"]),
                "preco": p["preco"], "era": p["era"], "desconto": p["desconto"], "selo": p["selo"], "imagem": p["imagem"],
                "link": f"https://www.amazon.com.br/dp/{p['asin']}?tag={LINK_TAG}", "eraSuspeito": susp, **campos_oferta(p),
                **({"ranking": {"pos": p["_rank"][0], "cat": p["_rank"][1]}} if "_rank" in p else {})}

    # categorias com menos de 3 itens: reaproveita anteriores ainda em estoque (getItems)
    ant = {c["id"]: c.get("itens", []) for c in antigo.get("categorias", [])}
    for cid, (cnome, final) in cats_out.items():
        if len(final) >= 3: continue
        velhos = [i["asin"] for i in ant.get(cid, []) if i["asin"] not in usados][:10]
        if not velhos: continue
        r = chamar(tok, "getItems", {"itemIds": velhos, "itemIdType": "ASIN", "marketplace": MKT,
                                     "partnerTag": TAG, "resources": res, "languagesOfPreference": ["pt_BR"]})
        for it in g(r, "itemsResult", "items") or []:
            p = ler(it)
            if p and em_estoque(p) and vendedor_ok(p) and p["asin"] not in usados and len(final) < MAX_POR_CAT:
                p["_kw"] = "anterior"; final.append(p); usados.add(p["asin"])
        log[cid] = "completada com itens anteriores"

    slot = slot_atual(agora)
    cat_json = {cid: ordenar_vitrine([para_json(p, cid) for p in final], hist, slot) for cid, (cn, final) in cats_out.items()}
    nomes_cat = {c[0]: c[1] for c in CATS}
    destaques = montar_destaques(cat_json, nomes_cat, agora.hour * 2 + agora.minute // 30)
    ja_dest = {i["asin"] for i in destaques}

    # Recomendados: maior desconto real x ticket, sem eraSuspeito e sem repetir os Destaques
    todos = [i for cid, its in cat_json.items() if cid != "bebidas" for i in its
             if not i["eraSuspeito"] and i["desconto"] > 0 and i["asin"] not in ja_dest]
    todos.sort(key=lambda i: -nota(i))
    dest, vist = [], set()
    for i in todos:
        ch = (i["nome"][:18].lower(), i["preco"])
        if ch in vist: continue
        vist.add(ch); dest.append(i)
        if len(dest) == 12: break

    saida = {"atualizadoEm": agora.strftime("%Y-%m-%dT%H:%M"),
             "categorias": [{"id": "destaques", "nome": "Destaques", "itens": destaques},
                            {"id": "recomendados", "nome": "Recomendados", "itens": dest},
                            {"id": "relampago", "nome": "Relâmpago", "itens": montar_relampago(cat_json, {c[0]: c[1] for c in CATS}, datetime.now(timezone.utc))},
                            {"id": "mais-vendidos", "nome": "Mais vendidos", "itens": [para_json(p, "mais-vendidos") for p in mv]}] +
                           [{"id": cid, "nome": cn, "itens": cat_json[cid]} for cid, cn, _, _ in CATS]}

    # histórico: 30 dias, só ASINs publicados
    limite = (agora - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    novo_hist = {}
    pub = {i["asin"]: i["preco"] for c in saida["categorias"] for i in c["itens"]}
    for asin, serie in hist.items():
        serie = [x for x in serie if x[0] >= limite]
        if serie: novo_hist[asin] = serie
    for asin, preco in pub.items():
        novo_hist.setdefault(asin, []).append([carimbo, preco])

    json.dump(saida, open(of_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(novo_hist, open(hi_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    resumo = {"atualizadoEm": saida["atualizadoEm"],
              "itens": {c["id"]: len(c["itens"]) for c in saida["categorias"]},
              "top3": [(i["nome"], i["desconto"], i["preco"]) for i in dest[:3]],
              "recursoImagem": [x for x in res if x.startswith("images.")], "obs": log}
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


MIN_DESC = {c[0]: c[2] for c in CATS}
DERIVADAS = ("destaques", "recomendados", "relampago")

def rapido(repo):
    """Modo rápido (Black Friday): revalida o preço de TODOS os produtos já publicados via getItems
    (10 por chamada, ~1–2 min), remove esgotados/sem oferta e refaz Destaques, Recomendados e Relâmpago."""
    agora = datetime.now(SP)
    carimbo = agora.strftime("%Y-%m-%d %H:%M")
    of_path, hi_path = os.path.join(repo, "ofertas.json"), os.path.join(repo, "historico.json")
    d = json.load(open(of_path, encoding="utf-8"))
    try: hist = json.load(open(hi_path, encoding="utf-8"))
    except Exception: hist = {}
    cats = {c["id"]: c for c in d["categorias"] if c["id"] not in DERIVADAS}
    asins = list(dict.fromkeys(i["asin"] for c in cats.values() for i in c["itens"]))
    tok = token(); novos, falhas = {}, 0
    for k in range(0, len(asins), 10):
        try:
            r = chamar(tok, "getItems", {"itemIds": asins[k:k + 10], "itemIdType": "ASIN", "marketplace": MKT,
                                         "partnerTag": TAG, "resources": RES, "languagesOfPreference": ["pt_BR"]})
        except ApiErro as e:
            if any(x in str(e) for x in ("HTTP 401", "HTTP 403", "token", "429 persistente", "rede")): raise
            falhas += 1; continue
        for it in g(r, "itemsResult", "items") or []:
            p = ler(it)
            if p: novos[p["asin"]] = p
    if not novos:
        raise ApiErro("getItems não devolveu nenhum produto")
    limite30 = (agora - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    removidos = 0
    for cid, c in cats.items():
        ficam = []
        for i in c["itens"]:
            p = novos.get(i["asin"])
            if p is None:
                ficam.append(i); continue          # lote falhou: mantém o dado anterior
            if not em_estoque(p) or p["desconto"] < (MIN_DESC.get(cid, 0) if cid != "mais-vendidos" else 0):
                removidos += 1; continue           # esgotou ou a oferta acabou
            i = {k: v for k, v in i.items() if k not in ("fim", "vendido", "primeExclusivo")}
            i.update({"preco": p["preco"], "era": p["era"], "desconto": p["desconto"], "selo": p["selo"],
                      "eraSuspeito": cid in ("eletronicos", "mais-vendidos") and p["desconto"] > 50,
                      **stats_hist(p["asin"], p["preco"], hist, limite30), **campos_oferta(p)})
            if p.get("imagem"): i["imagem"] = p["imagem"]
            ficam.append(i)
        c["itens"] = ficam
    slot = slot_atual(agora)
    for cid, c in cats.items():
        if cid != "mais-vendidos":
            c["itens"] = ordenar_vitrine(c["itens"], hist, slot)
    itens = {cid: c["itens"] for cid, c in cats.items()}
    nomes = {c[0]: c[1] for c in CATS}
    destaques = montar_destaques(itens, nomes, agora.hour * 2 + agora.minute // 30)
    ja_dest = {i["asin"] for i in destaques}
    rec = sorted([i for cid, its in itens.items() if cid not in ("bebidas", "mais-vendidos") for i in its
                  if not i.get("eraSuspeito") and i.get("desconto", 0) > 0 and i["asin"] not in ja_dest], key=lambda i: -nota(i))
    dest_rec, vist = [], set()
    for i in rec:
        ch = (i["nome"][:18].lower(), i["preco"])
        if ch in vist: continue
        vist.add(ch); dest_rec.append(i)
        if len(dest_rec) == 12: break
    d["atualizadoEm"] = agora.strftime("%Y-%m-%dT%H:%M")
    d["categorias"] = [{"id": "destaques", "nome": "Destaques", "itens": destaques},
                       {"id": "recomendados", "nome": "Recomendados", "itens": dest_rec},
                       {"id": "relampago", "nome": "Relâmpago", "itens": montar_relampago(itens, nomes, datetime.now(timezone.utc))}] + \
                      [c for c in d["categorias"] if c["id"] not in DERIVADAS]
    for c in d["categorias"]:
        if c["id"] in cats: c["itens"] = cats[c["id"]]["itens"]
    for asin, p in novos.items():
        hist.setdefault(asin, []).append([carimbo, p["preco"]])
    for asin in list(hist):
        hist[asin] = [x for x in hist[asin] if x[0] >= limite30]
        if not hist[asin]: del hist[asin]
    json.dump(d, open(of_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(hist, open(hi_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({"modo": "rapido", "atualizadoEm": d["atualizadoEm"], "revalidados": len(novos), "removidos": removidos,
                      "lotes_falhos": falhas, "itens": {c["id"]: len(c["itens"]) for c in d["categorias"]}}, ensure_ascii=False))


if __name__ == "__main__":
    if not os.environ.get("AMZ_CID") or not os.environ.get("AMZ_CSEC"):
        print("ERRO: defina AMZ_CID e AMZ_CSEC"); sys.exit(2)
    try:
        (rapido if os.environ.get("MODO") == "rapido" else main)(sys.argv[1] if len(sys.argv) > 1 else ".")
    except ApiErro as e:
        print("ERRO API (site não alterado):", str(e)[:400]); sys.exit(2)
