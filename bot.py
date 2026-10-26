"""Rota 77: Ofertas Automotivas (Carros, Motos, Peças e Ferramentas) → Telegram.
Anti-403: retry, delay, User-Agent de browser, categoria MLB1747.
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

# Categoria raiz: Acessórios para Veículos (MLB)
CAT_VEICULOS = "MLB1747"

SINAL_AUTO = re.compile(
    r"\b(carro|carros|automotivo|automotiva|automotivos|veicular|ve[ií]culo|"
    r"moto|motos|motocicleta|motociclista|capacete|bauleto|guid[aã]o|"
    r"pneu|pneus|[oó]leo|filtro|pastilha|freio|radiador|vela|igni[cç][aã]o|"
    r"multim[ií]dia|c[aâ]mera de r[eé]|camera de re|alarme|rastreador|"
    r"tapete|capa de banco|volante|insulfilm|politriz|pretinho|cera|"
    r"macaco|torqu[ií]metro|soquete|catraca|scanner|obd|"
    r"carregador veicular|compressor|calibrador|palheta|limpador|"
    r"parabrisa|estofado|soquete|chave de roda)\b",
    re.I,
)

BLOQUEIO = re.compile(
    r"\b(papel higi[eê]nico|fralda|batom|maquiagem|vestido|blusa feminina|"
    r"t[eê]nis corrida|whey|creatina|fone de ouvido|caixa de som boombox|"
    r"ventilador de coluna|liquidificador|air fryer|smartwatch|"
    r"rel[oó]gio de parede|brinquedo|boneca|coleira|antiparasit)\b",
    re.I,
)

GRUPOS = [
    {
        "nome": "Acessórios Internos e Conforto",
        "queries": [
            "tapete automotivo carro",
            "capa de banco automotiva",
            "suporte celular veicular",
            "organizador porta malas carro",
            "capa de volante carro",
            "aromatizante automotivo",
        ],
    },
    {
        "nome": "Som e Eletrônicos Veiculares",
        "queries": [
            "central multimídia automotiva",
            "rádio bluetooth carro",
            "câmera de ré automotiva",
            "sensor estacionamento carro",
            "carregador veicular turbo",
            "alarme automotivo",
        ],
    },
    {
        "nome": "Estética e Cuidados",
        "queries": [
            "cera automotiva carro",
            "shampoo automotivo",
            "pretinho pneu",
            "pano microfibra automotivo",
            "politriz automotiva",
            "kit estética automotiva",
        ],
    },
    {
        "nome": "Peças, Óleos e Iluminação",
        "queries": [
            "lâmpada led automotiva",
            "palheta limpador para-brisa",
            "filtro de óleo automotivo",
            "óleo 5w30 sintético",
            "aditivo radiador carro",
            "pastilha de freio carro",
        ],
    },
    {
        "nome": "Equipamentos para Motos",
        "queries": [
            "capacete moto integral",
            "luva motociclista",
            "capa de chuva moto",
            "suporte celular moto",
            "trava disco moto",
            "bauleto moto",
        ],
    },
    {
        "nome": "Ferramentas Automotivas",
        "queries": [
            "jogo soquetes automotivo",
            "torquímetro carro",
            "macaco hidráulico jacaré",
            "calibrador pneu digital",
            "carregador bateria 12v carro",
            "scanner OBD2 automotivo",
        ],
    },
]

S = requests.Session()
S.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
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
    if not SINAL_AUTO.search(titulo):
        return False
    return True


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


def ml_get(url, h, params=None, tentativas=3):
    """GET com retry em 403/429."""
    last = None
    for i in range(tentativas):
        try:
            r = S.get(url, headers=h or {}, params=params, timeout=25)
            last = r
            if r.status_code == 200:
                return r
            if r.status_code in (403, 429, 500, 502, 503):
                espera = 2 + i * 2 + random.uniform(0.5, 1.5)
                print(f"  HTTP {r.status_code} → retry em {espera:.1f}s ({i+1}/{tentativas})")
                time.sleep(espera)
                continue
            return r
        except Exception as e:
            print(f"  Request erro: {e}")
            time.sleep(2 + i)
    return last


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
    if not titulo_ok_automotivo(titulo):
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
    if not titulo_ok_automotivo(titulo):
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


def buscar_varios_query(query, h, vistos_ids, vistos_titulos, label, quantos):
    achados = []
    offset = random.choice([0, 0, 10, 20, 30])
    params = {
        "q": query,
        "category": CAT_VEICULOS,
        "limit": 50,
        "offset": offset,
        "sort": random.choice(["relevance", "price_asc", "sold_quantity_desc"]),
    }
    # 1) com token + categoria
    r = ml_get(f"{API}/sites/MLB/search", h, params=params)
    # 2) se 403, tenta sem Authorization
    if r is None or r.status_code == 403:
        print(f"  Search '{query}' com token falhou → tentando sem auth")
        time.sleep(1.5)
        r = ml_get(f"{API}/sites/MLB/search", {}, params=params)
    # 3) se ainda falhar, tenta sem category
    if r is None or r.status_code != 200:
        params2 = {k: v for k, v in params.items() if k != "category"}
        time.sleep(1.5)
        r = ml_get(f"{API}/sites/MLB/search", h or {}, params=params2)
    if r is None or r.status_code != 200:
        print(f"  Search '{query}' status {getattr(r, 'status_code', None)}")
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
            p = montar_produto(item["catalog_product_id"], h, label)
        if not p:
            p = produto_de_search_item(item, label)
        if not p:
            continue
        vistos_ids.add(p["id"])
        if nt:
            vistos_titulos.add(nt)
        achados.append(p)
        print(f"  OK [{label}] R$ {p['preco']:.2f} — {p['titulo'][:55]}")
    time.sleep(random.uniform(0.8, 1.6))  # evita rate limit
    return achados


def varios_do_grupo(grupo, h, vistos_ids, vistos_titulos, quantos):
    achados = []
    queries = list(grupo.get("queries", []))
    random.shuffle(queries)
    for q in queries:
        if len(achados) >= quantos:
            break
        falta = quantos - len(achados)
        novos = buscar_varios_query(q, h, vistos_ids, vistos_titulos, grupo["nome"], falta)
        achados.extend(novos)
    return achados


def montar_diversificado(h, estado):
    vistos_ids = set(estado["ids"].keys())
    vistos_titulos = set(estado["titulos"].keys())
    escolhidos = []
    grupos = list(GRUPOS)
    random.shuffle(grupos)
    for grupo in grupos:
        if len(escolhidos) >= MAX_POSTS:
            break
        n = min(POSTS_POR_GRUPO, MAX_POSTS - len(escolhidos))
        print(f"Grupo {grupo['nome']}: buscando até {n}")
        novos = varios_do_grupo(grupo, h, vistos_ids, vistos_titulos, n)
        escolhidos.extend(novos)
    return escolhidos


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
    print(f"Meta: {POSTS_POR_GRUPO} por grupo, máx {MAX_POSTS} total")
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
        print("Nada a postar")
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
            time.sleep(1.2)
    salvar_estado(estado)
    print("Postagens enviadas:", enviados)


if __name__ == "__main__":
    main()
