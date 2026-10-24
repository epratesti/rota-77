"""Rota 77: Ofertas Automotivas (Carros, Motos, Peças e Ferramentas) → Telegram.
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
        "queries": [
            "jogo tapete carro automotivo", "capa banco automotiva", "suporte celular carro veicular",
            "organizador porta malas carro", "capa volante automotiva", "aromatizante automotivo carro",
            "lixeira para carro automotiva", "insulfilm automotivo",
        ],
    },
    {
        "nome": "Som e Eletrônicos Veiculares",
        "queries": [
            "central multimidia automotiva", "radio bluetooth automotivo", "camera de re automotiva",
            "sensor de estacionamento carro", "carregador veicular turbo carro", "rastreador veicular gps",
            "modulo amplificador automotivo", "alto falante porta carro", "alarme automotivo carro",
        ],
    },
    {
        "nome": "Estética e Cuidados Automotivos",
        "queries": [
            "cera cristalizadora automotiva", "shampoo automotivo neutro carro", "pretinho pneu automotivo",
            "pano microfibra automotivo detalhamento", "politriz automotiva carro", "revitalizador de plasticos automotivo",
            "limpa estofados automotivo", "kit estetica automotiva carro",
        ],
    },
    {
        "nome": "Peças, Óleos e Iluminação",
        "queries": [
            "lampada led super branca automotiva", "palheta limpador parabrisa carro", "filtro de oleo automotivo",
            "oleo 5w30 sintetico automotivo", "aditivo radiador concentrado carro", "kit pastilha de freio carro",
            "reparador de pneu spray automotivo", "vela de ignição iridium carro",
        ],
    },
    {
        "nome": "Equipamentos para Motos",
        "queries": [
            "capacete moto motociclista", "luva motociclista moto", "capa de chuva motociclista moto",
            "suporte celular moto guidao", "trava de disco moto alarme", "intercomunicador capacete moto",
            "jaqueta motociclista moto", "bauleto moto bau",
        ],
    },
    {
        "nome": "Ferramentas Automotivas",
        "queries": [
            "jogo de soquetes catraca automotivo", "torquimetro automotivo", "macaco hidraulico jacare automotivo",
            "calibrador pneu digital veicular", "carregador de bateria automotivo 12v", "chave de roda cruz automotiva",
            "compressor de ar veicular 12v carro", "scanner automotivo obd2",
        ],
    },
]

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
