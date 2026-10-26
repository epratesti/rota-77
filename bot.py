"""Rota 77: Ofertas Automotivas → Telegram.
Estratégia: highlights por categoria (mais estável no GitHub Actions).
Search só como fallback rápido (1 tentativa, sem loop longo).
Horário SP: 07h–22h.
"""
import os, json, html, re, random, time, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

AFF_ID = os.getenv("ML_AFFILIATE_ID", "71970283")
AFF_PARAMS = os.getenv("ML_AFFILIATE_PARAMS", "matt_tool={id}")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
POSTS_POR_GRUPO = int(os.getenv("POSTS_POR_GRUPO", "1"))
MAX_POSTS = int(os.getenv("MAX_POSTS", "6"))
REPETIR_APOS_DIAS = int(os.getenv("REPETIR_APOS_DIAS", "14"))
API = "https://api.mercadolibre.com"
ROOT = Path(__file__).parent
TRENDS = ROOT / "docs" / "trends.json"
STATE = ROOT / "state" / "posted.json"
TZ = ZoneInfo("America/Sao_Paulo")

# Categorias automotivas MLB (highlights costuma funcionar quando /search dá 403)
CATS = [
    ("MLB1747", "Acessórios para Veículos"),
    ("MLB3381", "Áudio e Vídeo para Carros"),
    ("MLB455185", "Peças de Carros e Caminhonetes"),
    ("MLB1771", "Motos"),
    ("MLB455186", "Peças de Moto"),
    ("MLB2227", "Ferramentas"),
]

SINAL_AUTO = re.compile(
    r"\b(carro|carros|automotivo|automotiva|automotivos|veicular|ve[ií]culo|"
    r"moto|motos|motocicleta|motociclista|capacete|bauleto|guid[aã]o|"
    r"pneu|pneus|[oó]leo|filtro|pastilha|freio|radiador|vela|igni[cç][aã]o|"
    r"multim[ií]dia|c[aâ]mera de r[eé]|camera de re|alarme|rastreador|"
    r"tapete|capa de banco|volante|insulfilm|politriz|pretinho|cera|"
    r"macaco|torqu[ií]metro|soquete|catraca|scanner|obd|"
    r"carregador veicular|compressor|calibrador|palheta|limpador|"
    r"parabrisa|estofado|chave de roda|jacar[eé]|hidr[aá]ulico)\b",
    re.I,
)

BLOQUEIO = re.compile(
    r"\b(papel higi[eê]nico|fralda|batom|maquiagem|vestido|blusa feminina|"
    r"t[eê]nis corrida|whey|creatina|fone de ouvido|caixa de som boombox|"
    r"ventilador de coluna|liquidificador|air fryer|smartwatch|"
    r"rel[oó]gio de parede|brinquedo|boneca|coleira|antiparasit)\b",
    re.I,
)

QUERIES_FALLBACK = [
    "tapete automotivo",
    "capacete moto",
    "central multimídia carro",
    "câmera de ré automotiva",
    "cera automotiva",
    "óleo 5w30",
    "macaco hidráulico",
    "bauleto moto",
    "alarme automotivo",
    "scanner obd2",
]

S = requests.Session()
S.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
})


def headers_ml():
    cid, sec = os.getenv("ML_CLIENT_ID"), os.getenv("ML_CLIENT_SECRET")
    if not (cid and sec):
        print("ERRO: secrets ML ausentes")
        return {}
    r = S.post(
        f"{API}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": sec,
        },
        timeout=20,
    )
    r.raise_for_status()
    print("Token ML OK")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def link_afiliado(url):
    sep = "&" if "?" in url else "?"
    return url + sep + AFF_PARAMS.format(id=AFF_ID)


def normalizar_titulo(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9áéíóúâêôãõç\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80]


def titulo_ok_automotivo(titulo: str) -> bool:
    if not titulo:
        return False
    if BLOQUEIO.search(titulo):
        return False
    # Em highlights de cat automotiva, relaxa um pouco o sinal
    return True if SINAL_AUTO.search(titulo) else False


def carregar_estado():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = STATE.read_text(encoding="utf-8").strip() or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"ids": {}, "titulos": {}}
        if data and "ids" not in data:
            return {"ids": data, "titulos": {}}
        data.setdefault("ids", {})
        data.setdefault("titulos", {})
        return data
    except Exception as e:
        print("Aviso: estado inválido, reiniciando:", e)
        return {"ids": {}, "titulos": {}}


def limpar_estado(estado, agora):
    limite = agora - dt.timedelta(days=REPETIR_APOS_DIAS)
    ids_limpos, titulos_limpos = {}, {}
    for k, v in estado.get("ids", {}).items():
        try:
            if dt.datetime.fromisoformat(v) > limite:
                ids_limpos[k] = v
        except Exception:
            continue
    for k, v in estado.get("titulos", {}).items():
        try:
            if dt.datetime.fromisoformat(v) > limite:
                titulos_limpos[k] = v
        except Exception:
            continue
    return {"ids": ids_limpos, "titulos": titulos_limpos}


def ja_postado(estado, pid, titulo):
    if pid in estado["ids"]:
        return True
    nt = normalizar_titulo(titulo)
    return bool(nt and nt in estado["titulos"])


def registrar_postado(estado, pid, titulo, agora):
    estado["ids"][pid] = agora.isoformat()
    nt = normalizar_titulo(titulo)
    if nt:
        estado["titulos"][nt] = agora.isoformat()


def escolher_oferta(results):
    if not results:
        return None
    validos = []
    for it in results:
        try:
            preco = float(it.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if preco <= 0:
            continue
        frete = (it.get("shipping") or {}).get("free_shipping", False)
        validos.append({"item": it, "preco": preco, "frete": frete})
    if not validos:
        return None
    precos = sorted(v["preco"] for v in validos)
    mediana = precos[len(precos) // 2]
    piso = mediana * 0.30 if mediana > 0 else 0
    validos = [v for v in validos if v["preco"] >= piso] or validos
    com_frete = [v for v in validos if v["frete"]]
    pool = com_frete if com_frete else validos
    return min(pool, key=lambda x: x["preco"])


def ml_get(url, h, params=None):
    try:
        r = S.get(url, headers=h or {}, params=params, timeout=20)
        return r
    except Exception as e:
        print(f"  Request erro: {e}")
        return None


def montar_produto(pid, h, categoria):
    titulo, foto = "", ""
    preco, frete = 0.0, False
    item_id = None
    try:
        rp = ml_get(f"{API}/products/{pid}", h)
        if rp is not None and rp.status_code == 200:
            d = rp.json()
            titulo = d.get("name") or d.get("title") or ""
            pics = d.get("pictures") or []
            if pics:
                foto = (pics[0].get("url") or pics[0].get("secure_url") or "").replace(
                    "http://", "https://"
                )
    except Exception as e:
        print(f"  products/{pid}:", e)
    if titulo and BLOQUEIO.search(titulo):
        return None
    # Em categoria automotiva, aceita se tiver sinal OU se veio de highlight de cat auto
    if titulo and not SINAL_AUTO.search(titulo):
        # ainda permite se categoria for claramente auto
        if "moto" not in categoria.lower() and "veícul" not in categoria.lower() and "carro" not in categoria.lower() and "áudio" not in categoria.lower() and "peça" not in categoria.lower() and "ferrament" not in categoria.lower():
            return None
    try:
        ri = ml_get(f"{API}/products/{pid}/items", h)
        if ri is not None and ri.status_code == 200:
            escolha = escolher_oferta(ri.json().get("results") or [])
            if escolha:
                preco = escolha["preco"]
                frete = escolha["frete"]
                item_id = escolha["item"].get("id") or escolha["item"].get("item_id")
    except Exception as e:
        print(f"  items/{pid}:", e)
    if not titulo or preco <= 0:
        return None
    if item_id:
        mid = str(item_id)
        mid_fmt = (mid[:3] + "-" + mid[3:]) if mid.startswith("MLB") and "-" not in mid else mid
        link = link_afiliado(f"https://produto.mercadolivre.com.br/{mid_fmt}")
    else:
        link = link_afiliado(f"https://www.mercadolivre.com.br/p/{pid}")
    return {
        "id": pid,
        "titulo": titulo,
        "preco": preco,
        "imagem": foto,
        "frete_gratis": frete,
        "categoria": categoria,
        "link": link,
        "item_id": item_id,
    }


def produto_de_search_item(item, categoria_label):
    titulo = item.get("title") or ""
    if BLOQUEIO.search(titulo):
        return None
    if not SINAL_AUTO.search(titulo):
        return None
    try:
        preco = float(item.get("price") or 0)
    except (TypeError, ValueError):
        return None
    if not titulo or preco <= 0:
        return None
    frete = (item.get("shipping") or {}).get("free_shipping", False)
    foto = (item.get("thumbnail") or "").replace("http://", "https://")
    mid = str(item.get("id", ""))
    pid = item.get("catalog_product_id") or mid
    mid_fmt = (mid[:3] + "-" + mid[3:]) if mid.startswith("MLB") and "-" not in mid else mid
    return {
        "id": str(pid),
        "titulo": titulo,
        "preco": preco,
        "imagem": foto,
        "frete_gratis": frete,
        "categoria": categoria_label,
        "link": link_afiliado(f"https://produto.mercadolivre.com.br/{mid_fmt}"),
        "item_id": mid,
    }


def buscar_highlights(cat_id, nome, h, vistos_ids, vistos_titulos, quantos):
    achados = []
    r = ml_get(f"{API}/highlights/MLB/category/{cat_id}", h)
    if r is None or r.status_code != 200:
        print(f"  Highlights {cat_id} ({nome}): status {getattr(r, 'status_code', None)}")
        return achados
    try:
        items = list(r.json().get("content", [])[:40])
    except Exception:
        return achados
    random.shuffle(items)
    for item in items:
        if len(achados) >= quantos:
            break
        pid = item.get("id")
        if not pid or pid in vistos_ids:
            continue
        p = montar_produto(pid, h, nome)
        if not p:
            continue
        nt = normalizar_titulo(p["titulo"])
        if nt and nt in vistos_titulos:
            continue
        vistos_ids.add(p["id"])
        if nt:
            vistos_titulos.add(nt)
        achados.append(p)
        print(f"  OK [hl/{nome}] R$ {p['preco']:.2f} — {p['titulo'][:55]}")
    return achados


def buscar_por_categoria(cat_id, nome, h, vistos_ids, vistos_titulos, quantos):
    """Lista itens da categoria (sem q) — às vezes passa quando search com q dá 403."""
    achados = []
    offset = random.choice([0, 10, 20, 30, 50])
    params = {"category": cat_id, "limit": 50, "offset": offset, "sort": "relevance"}
    r = ml_get(f"{API}/sites/MLB/search", h, params=params)
    if r is None or r.status_code != 200:
        print(f"  Category search {cat_id}: status {getattr(r, 'status_code', None)}")
        return achados
    try:
        results = r.json().get("results") or []
    except Exception:
        return achados
    random.shuffle(results)
    for item in results:
        if len(achados) >= quantos:
            break
        pid = item.get("catalog_product_id") or item.get("id")
        if not pid or str(pid) in vistos_ids:
            continue
        nt = normalizar_titulo(item.get("title") or "")
        if nt and nt in vistos_titulos:
            continue
        p = None
        if item.get("catalog_product_id"):
            p = montar_produto(item["catalog_product_id"], h, nome)
        if not p:
            p = produto_de_search_item(item, nome)
        if not p:
            continue
        vistos_ids.add(p["id"])
        if nt:
            vistos_titulos.add(nt)
        achados.append(p)
        print(f"  OK [cat/{nome}] R$ {p['preco']:.2f} — {p['titulo'][:55]}")
    return achados


def buscar_query_rapida(query, h, vistos_ids, vistos_titulos, quantos):
    """Uma tentativa só — sem retry longo."""
    achados = []
    params = {"q": query, "limit": 30, "offset": 0, "sort": "relevance"}
    r = ml_get(f"{API}/sites/MLB/search", h, params=params)
    if r is None or r.status_code != 200:
        print(f"  Query '{query}': status {getattr(r, 'status_code', None)}")
        return achados
    try:
        results = r.json().get("results") or []
    except Exception:
        return achados
    random.shuffle(results)
    for item in results:
        if len(achados) >= quantos:
            break
        pid = item.get("catalog_product_id") or item.get("id")
        if not pid or str(pid) in vistos_ids:
            continue
        nt = normalizar_titulo(item.get("title") or "")
        if nt and nt in vistos_titulos:
            continue
        p = produto_de_search_item(item, "Automotivo")
        if not p:
            continue
        vistos_ids.add(p["id"])
        if nt:
            vistos_titulos.add(nt)
        achados.append(p)
        print(f"  OK [q] R$ {p['preco']:.2f} — {p['titulo'][:55]}")
    return achados


def montar_diversificado(h, estado):
    vistos_ids = set(estado["ids"].keys())
    vistos_titulos = set(estado["titulos"].keys())
    escolhidos = []

    cats = list(CATS)
    random.shuffle(cats)

    # 1) Highlights por categoria
    for cat_id, nome in cats:
        if len(escolhidos) >= MAX_POSTS:
            break
        falta = MAX_POSTS - len(escolhidos)
        n = min(POSTS_POR_GRUPO, falta)
        print(f"Highlights {nome} ({cat_id}): até {n}")
        novos = buscar_highlights(cat_id, nome, h, vistos_ids, vistos_titulos, n)
        escolhidos.extend(novos)
        time.sleep(0.4)

    # 2) Search só por category= (sem texto)
    if len(escolhidos) < MAX_POSTS:
        for cat_id, nome in cats:
            if len(escolhidos) >= MAX_POSTS:
                break
            falta = MAX_POSTS - len(escolhidos)
            print(f"Category list {nome}: até {falta}")
            novos = buscar_por_categoria(cat_id, nome, h, vistos_ids, vistos_titulos, min(2, falta))
            escolhidos.extend(novos)
            time.sleep(0.4)

    # 3) Queries curtas (1 tentativa cada)
    if len(escolhidos) < MAX_POSTS:
        qs = list(QUERIES_FALLBACK)
        random.shuffle(qs)
        for q in qs[:6]:
            if len(escolhidos) >= MAX_POSTS:
                break
            falta = MAX_POSTS - len(escolhidos)
            novos = buscar_query_rapida(q, h, vistos_ids, vistos_titulos, min(1, falta))
            escolhidos.extend(novos)

    return escolhidos[:MAX_POSTS]


def preco_br(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def postar(p):
    cat = html.escape(p.get("categoria", ""))
    titulo = html.escape(p["titulo"][:120])
    preco = preco_br(p["preco"])
    link = html.escape(p["link"])
    frete_linha = "🚚 <b>Frete grátis</b>\n" if p.get("frete_gratis") else ""
    preco_label = f"a partir de <b>{preco}</b>" if p.get("item_id") else f"<b>{preco}</b>"
    texto = (
        f"🚗 <b>Rota 77 — {cat}</b>\n\n"
        f"📦 {titulo}\n\n"
        f"💰 {preco_label}\n"
        f"{frete_linha}"
        f"\n👉 <a href=\"{link}\">Ver oferta no Mercado Livre</a>\n\n"
        f"<i>Link de afiliado · Preços podem variar</i>"
    )
    if not TG_TOKEN or not TG_CHAT:
        print("Telegram não configurado")
        return False
    data = {"chat_id": TG_CHAT, "parse_mode": "HTML"}
    if p.get("imagem"):
        data["photo"] = p["imagem"]
        data["caption"] = texto
        r = S.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", data=data, timeout=30
        )
    else:
        data["text"] = texto
        r = S.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=30
        )
    print("Telegram:", r.status_code, r.text[:150])
    return r.ok


def pode_postar_agora(agora: dt.datetime) -> bool:
    return 7 <= agora.hour <= 22


def salvar_estado(estado):
    STATE.write_text(
        json.dumps(estado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    agora = dt.datetime.now(TZ)
    print("Iniciando Rota 77", agora.isoformat())
    print(f"Meta: até {MAX_POSTS} posts (highlights + categorias)")
    h = headers_ml()
    if not h:
        return
    estado = limpar_estado(carregar_estado(), agora)
    print(f"Bloqueados (últimos {REPETIR_APOS_DIAS} dias):", len(estado["ids"]))
    ranking = montar_diversificado(h, estado)
    print("Produtos selecionados:", len(ranking))
    TRENDS.parent.mkdir(parents=True, exist_ok=True)
    trends_itens = [{k: v for k, v in p.items() if k != "item_id"} for p in ranking]
    TRENDS.write_text(
        json.dumps(
            {"atualizado": agora.isoformat(), "itens": trends_itens},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not ranking:
        print("Nada a postar — se só 403, IP do GitHub Actions está bloqueado pelo ML")
        salvar_estado(estado)
        return
    if not (TG_TOKEN and TG_CHAT):
        print("Falta Telegram")
        return
    if not pode_postar_agora(agora):
        print(f"Fora do horário ({agora.hour}h)")
        salvar_estado(estado)
        return
    enviados = 0
    for p in ranking:
        if enviados >= MAX_POSTS:
            break
        if ja_postado(estado, p["id"], p["titulo"]):
            continue
        if postar(p):
            registrar_postado(estado, p["id"], p["titulo"], agora)
            enviados += 1
            salvar_estado(estado)
            time.sleep(1.0)
    salvar_estado(estado)
    print("Postagens enviadas:", enviados)


if __name__ == "__main__":
    main()
