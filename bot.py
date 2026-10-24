"""Rota 77: Ofertas Exclusivamente Automotivas (Carros, Motos, Peças e Ferramentas) → Telegram.
Bloqueio por ID, item_id e fingerprint de título.
Horário SP: 07h–22h.
Inclui o recurso 'Luck Lock' (Achado da Sorte).
"""
import os, json, html, re, random, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

AFF_ID = os.getenv("ML_AFFILIATE_ID", "71970283")
AFF_PARAMS = os.getenv("ML_AFFILIATE_PARAMS", "matt_tool={id}")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
POSTS_POR_GRUPO = int(os.getenv("POSTS_POR_GRUPO", "1"))
MAX_POSTS = int(os.getenv("MAX_POSTS", "4"))
REPETIR_APOS_DIAS = int(os.getenv("REPETIR_APOS_DIAS", "14"))
API = "https://api.mercadolibre.com"
ROOT = Path(__file__).parent
TRENDS = ROOT / "docs" / "trends.json"
STATE = ROOT / "state" / "posted.json"
TZ = ZoneInfo("America/Sao_Paulo")

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "em", "com", "para", "por", "um", "uma",
    "o", "a", "os", "as", "no", "na", "nos", "nas", "ao", "à", "ou", "x", "un",
    "unidades", "unidade", "kit", "original", "novo", "nova", "preto", "branco",
    "azul", "vermelho", "cor", "tamanho", "ml", "kg", "g", "cm", "mm", "w",
    "carro", "moto", "par", "jogo", "universal"
}

GRUPOS = [
    {
        "nome": "Acessórios Internos e Conforto",
        "cats": ["MLB1743"],
        "queries": [
            "jogo tapete carro automotivo", "capa banco automotiva", "suporte celular carro veicular",
            "organizador porta malas carro", "capa volante automotiva", "aromatizante automotivo carro",
            "lixeira para carro automotiva", "insulfilm automotivo",
        ],
    },
    {
        "nome": "Som e Eletrônicos Veiculares",
        "cats": ["MLB1743"],
        "queries": [
            "central multimidia automotiva", "radio bluetooth automotivo", "camera de re automotiva",
            "sensor de estacionamento carro", "carregador veicular turbo carro", "rastreador veicular gps",
            "modulo amplificador automotivo", "alto falante porta carro", "alarme automotivo carro",
        ],
    },
    {
        "nome": "Estética e Cuidados Automotivos",
        "cats": ["MLB1743"],
        "queries": [
            "cera cristalizadora automotiva", "shampoo automotivo neutro carro", "pretinho pneu automotivo",
            "pano microfibra automotivo detalhamento", "politriz automotiva carro", "revitalizador de plasticos automotivo",
            "limpa estofados automotivo", "kit estetica automotiva carro",
        ],
    },
    {
        "nome": "Peças, Óleos e Iluminação",
        "cats": ["MLB1743"],
        "queries": [
            "lampada led super branca automotiva", "palheta limpador parabrisa carro", "filtro de oleo automotivo",
            "oleo 5w30 sintetico automotivo", "aditivo radiador concentrado carro", "kit pastilha de freio carro",
            "reparador de pneu spray automotivo", "vela de ignição iridium carro",
        ],
    },
    {
        "nome": "Equipamentos para Motos",
        "cats": ["MLB1743"],
        "queries": [
            "capacete moto motociclista", "luva motociclista moto", "capa de chuva motociclista moto",
            "suporte celular moto guidao", "trava de disco moto alarme", "intercomunicador capacete moto",
            "jaqueta motociclista moto", "bauleto moto bau",
        ],
    },
    {
        "nome": "Ferramentas Automotivas",
        "cats": ["MLB1743"],
        "queries": [
            "jogo de soquetes catraca automotivo", "torquimetro automotivo", "macaco hidraulico jacare automotivo",
            "calibrador pneu digital veicular", "carregador de bateria automotivo 12v", "chave de roda cruz automotiva",
            "compressor de ar veicular 12v carro", "scanner automotivo obd2",
        ],
    },
]

CAT_NOMES = {
    "MLB1743": "Acessórios Veiculares",
}

S = requests.Session()
S.headers.update({"User-Agent": "rota-77-auto/1.0", "Accept": "application/json"})


def headers_ml():
    cid, sec = os.getenv("ML_CLIENT_ID"), os.getenv("ML_CLIENT_SECRET")
    if not (cid and sec):
        print("ERRO: secrets ML ausentes")
        return {}
    r = S.post(f"{API}/oauth/token", data={
        "grant_type": "client_credentials", "client_id": cid, "client_secret": sec
    }, timeout=20)
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
    return t[:100]


def fingerprint(t: str) -> str:
    nt = normalizar_titulo(t)
    palavras = []
    for w in nt.split():
        if len(w) < 3 or w in STOPWORDS:
            continue
        if w.isdigit():
            continue
        palavras.append(w)
    chave = " ".join(sorted(palavras[:8]))
    return chave[:90] if chave else nt[:60]


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


def incorporar_trends(estado, agora):
    if REPETIR_APOS_DIAS <= 0:
        return estado
    try:
        if not TRENDS.exists():
            return estado
        data = json.loads(TRENDS.read_text(encoding="utf-8") or "{}")
        itens = data.get("itens") or []
        ts = data.get("atualizado") or agora.isoformat()
        for it in itens:
            pid = str(it.get("id") or "")
            titulo = it.get("titulo") or ""
            if pid:
                estado["ids"][pid] = ts
            for key in (normalizar_titulo(titulo), fingerprint(titulo)):
                if key:
                    estado["titulos"][key] = ts
        print(f"Trends incorporados: {len(itens)} itens")
    except Exception as e:
        print("Aviso ao ler trends:", e)
    return estado


def limpar_estado(estado, agora):
    if REPETIR_APOS_DIAS <= 0:
        return {"ids": {}, "titulos": {}}
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


def ja_postado(estado, pid, titulo, item_id=None):
    if REPETIR_APOS_DIAS <= 0:
        return False
    ids = estado.get("ids", {})
    if str(pid) in ids:
        return True
    if item_id and str(item_id) in ids:
        return True
    for cand in (str(pid), str(item_id or "")):
        if not cand:
            continue
        alt = cand.replace("MLB-", "MLB").replace("MLB", "MLB-") if cand.startswith("MLB") else cand
        if alt in ids:
            return True
    titulos = estado.get("titulos", {})
    nt = normalizar_titulo(titulo)
    fp = fingerprint(titulo)
    if nt and nt in titulos:
        return True
    if fp and fp in titulos:
        return True
    if fp:
        fp_tokens = set(fp.split())
        if len(fp_tokens) >= 3:
            for t in titulos:
                other = set(t.split())
                if len(fp_tokens & other) >= min(4, len(fp_tokens)):
                    return True
    return False


def registrar_postado(estado, pid, titulo, agora, item_id=None):
    if REPETIR_APOS_DIAS <= 0:
        return
    ts = agora.isoformat()
    estado.setdefault("ids", {})[str(pid)] = ts
    if item_id:
        estado["ids"][str(item_id)] = ts
        mid = str(item_id)
        if mid.startswith("MLB") and "-" not in mid:
            estado["ids"][mid[:3] + "-" + mid[3:]] = ts
    nt = normalizar_titulo(titulo)
    fp = fingerprint(titulo)
    if nt:
        estado.setdefault("titulos", {})[nt] = ts
    if fp:
        estado.setdefault("titulos", {})[fp] = ts


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


def montar_produto(pid, h, categoria):
    titulo, foto = "", ""
    preco, frete = 0.0, False
    item_id = None
    try:
        rp = S.get(f"{API}/products/{pid}", headers=h, timeout=15)
        if rp.status_code == 200:
            d = rp.json()
            titulo = d.get("name") or d.get("title") or ""
            pics = d.get("pictures") or []
            if pics:
                foto = (pics[0].get("url") or pics[0].get("secure_url") or "").replace("http://", "https://")
    except Exception as e:
        print(f"  products/{pid}:", e)
    try:
        ri = S.get(f"{API}/products/{pid}/items", headers=h, timeout=15)
        if ri.status_code == 200:
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
        "id": str(pid), "titulo": titulo, "preco": preco, "imagem": foto,
        "frete_gratis": frete, "categoria": categoria, "link": link, "item_id": item_id,
        "is_luck_lock": False,
    }


def produto_de_search_item(item, categoria_label):
    titulo = item.get("title") or ""
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
        "id": str(pid), "titulo": titulo, "preco": preco, "imagem": foto,
        "frete_gratis": frete, "categoria": categoria_label,
        "link": link_afiliado(f"https://produto.mercadolivre.com.br/{mid_fmt}"),
        "item_id": mid,
        "is_luck_lock": False,
    }


def _marcar_visto(vistos_ids, vistos_fps, p):
    vistos_ids.add(p["id"])
    if p.get("item_id"):
        vistos_ids.add(str(p["item_id"]))
    fp = fingerprint(p["titulo"])
    if fp:
        vistos_fps.add(fp)
    nt = normalizar_titulo(p["titulo"])
    if nt:
        vistos_fps.add(nt)


def _ja_visto(vistos_ids, vistos_fps, pid, mid, titulo):
    if pid in vistos_ids or (mid and mid in vistos_ids):
        return True
    fp = fingerprint(titulo)
    nt = normalizar_titulo(titulo)
    if fp and fp in vistos_fps:
        return True
    if nt and nt in vistos_fps:
        return True
    if fp:
        tokens = set(fp.split())
        if len(tokens) >= 3:
            for t in vistos_fps:
                if len(tokens & set(t.split())) >= min(4, len(tokens)):
                    return True
    return False


def buscar_varios_query(query, cat_id, h, vistos_ids, vistos_fps, label, quantos):
    achados = []
    try:
        # Posição inicial levemente variada para garantir novos produtos
        offset = random.choice([0, 10, 20])
        params = {
            "q": query, "limit": 50, "offset": offset,
            "category": "MLB1743", # Força categoria 'Acessórios para Veículos'
            "sort": random.choice(["relevance", "sold_quantity_desc"]),
        }
        r = S.get(f"{API}/sites/MLB/search", headers=h, params=params, timeout=25)
        if r.status_code != 200:
            return achados
        results = r.json().get("results") or []
        random.shuffle(results)
        for item in results:
            if len(achados) >= quantos:
                break
            pid = str(item.get("catalog_product_id") or item.get("id") or "")
            mid = str(item.get("id") or "")
            titulo = item.get("title") or ""
            if not pid or _ja_visto(vistos_ids, vistos_fps, pid, mid, titulo):
                continue
            p = None
            if item.get("catalog_product_id"):
                p = montar_produto(item["catalog_product_id"], h, label)
            if not p:
                p = produto_de_search_item(item, label)
            if not p:
                continue
            if _ja_visto(vistos_ids, vistos_fps, p["id"], str(p.get("item_id") or ""), p["titulo"]):
                continue
            _marcar_visto(vistos_ids, vistos_fps, p)
            achados.append(p)
            print(f"  OK [{label}] R$ {p['preco']:.2f} — {p['titulo'][:50]}")
    except Exception as e:
        print(f"Erro search '{query}':", e)
    return achados


def varios_do_grupo(grupo, h, vistos_ids, vistos_fps, quantos):
    achados = []
    queries = list(grupo.get("queries", []))
    random.shuffle(queries)
    for q in queries:
        if len(achados) >= quantos:
            break
        falta = quantos - len(achados)
        novos = buscar_varios_query(q, "MLB1743", h, vistos_ids, vistos_fps, grupo["nome"], falta)
        achados.extend(novos)
    return achados


def montar_diversificado(h, estado):
    vistos_ids = set(str(k) for k in estado.get("ids", {}).keys())
    vistos_fps = set(estado.get("titulos", {}).keys())
    escolhidos = []
    grupos = list(GRUPOS)
    random.shuffle(grupos)
    for grupo in grupos:
        if len(escolhidos) >= MAX_POSTS:
            break
        falta_total = MAX_POSTS - len(escolhidos)
        n = min(POSTS_POR_GRUPO, falta_total)
        print(f"Grupo {grupo['nome']}: buscando até {n} (bloqueados: {len(vistos_ids)} ids)")
        novos = varios_do_grupo(grupo, h, vistos_ids, vistos_fps, n)
        escolhidos.extend(novos)
    
    if escolhidos:
        sorteado = random.choice(escolhidos)
        sorteado["is_luck_lock"] = True
        print(f"🍀 Luck Lock ativado para: {sorteado['titulo'][:50]}")

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
    
    if p.get("is_luck_lock"):
        cabecalho = "🍀 <b>Rota 77 — Achado da Sorte (Luck Lock)</b> 🍀"
    else:
        cabecalho = f"🏎️ <b>Rota 77 — {cat}</b>"

    texto = (
        f"{cabecalho}\n\n"
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
        r = S.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", data=data, timeout=30)
    else:
        data["text"] = texto
        r = S.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=30)
    print("Telegram:", r.status_code, r.text[:150])
    return r.ok


def pode_postar_agora(agora: dt.datetime) -> bool:
    return 7 <= agora.hour <= 22


def salvar_estado(estado):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    agora = dt.datetime.now(TZ)
    print("Iniciando Rota 77 Automotivo", agora.isoformat())
    print(f"Meta: {POSTS_POR_GRUPO}/grupo, máx {MAX_POSTS} | bloqueio {REPETIR_APOS_DIAS} dias")
    h = headers_ml()
    if not h:
        return
    estado = limpar_estado(carregar_estado(), agora)
    estado = incorporar_trends(estado, agora)
    print(f"Bloqueados: {len(estado.get('ids', {}))} ids, {len(estado.get('titulos', {}))} fingerprints")
    ranking = montar_diversificado(h, estado)
    ranking = [p for p in ranking if not ja_postado(estado, p["id"], p["titulo"], p.get("item_id"))]
    print("Selecionados após filtro:", len(ranking))
    TRENDS.parent.mkdir(parents=True, exist_ok=True)
    trends_itens = [{k: v for k, v in p.items() if k != "item_id"} for p in ranking]
    TRENDS.write_text(json.dumps({"atualizado": agora.isoformat(), "itens": trends_itens},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    if not ranking:
        print("Nada novo para postar")
        salvar_estado(estado)
        return
    if not (TG_TOKEN and TG_CHAT):
        print("Falta Telegram")
        salvar_estado(estado)
        return
    if not pode_postar_agora(agora):
        print(f"Fora do horário ({agora.hour}h) — sem postar")
        salvar_estado(estado)
        return
    enviados = 0
    for p in ranking:
        if enviados >= MAX_POSTS:
            break
        if ja_postado(estado, p["id"], p["titulo"], p.get("item_id")):
            print(f"  Pula: {p['titulo'][:50]}")
            continue
        if postar(p):
            registrar_postado(estado, p["id"], p["titulo"], agora, p.get("item_id"))
            enviados += 1
            salvar_estado(estado)
    salvar_estado(estado)
    print("Postagens enviadas:", enviados)
    print(f"Estado: {len(estado.get('ids', {}))} ids bloqueados")


if __name__ == "__main__":
    main()
