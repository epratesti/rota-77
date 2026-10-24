# Rota 77

Radar de ofertas do Mercado Livre com publicação automática no Telegram.

Baseado no [radar-ml](https://github.com/epratesti/radar-ml), com anti-repetição (14 dias), fingerprint de título e merge seguro de estado.

## Configuração

No GitHub → **Settings → Secrets and variables → Actions**, configure:

| Secret | Descrição |
|--------|-----------|
| `TELEGRAM_TOKEN` | Token do bot do Telegram |
| `TELEGRAM_CHAT_ID` | ID do canal/grupo |
| `ML_CLIENT_ID` | App ID Mercado Livre |
| `ML_CLIENT_SECRET` | Secret Mercado Livre |

Opcional no workflow: `ML_AFFILIATE_ID`, `POSTS_POR_GRUPO`, `MAX_POSTS`, `REPETIR_APOS_DIAS`.

## Execução

- Agendada: 1x por hora (cron `:45` UTC)
- Manual: **Actions → Rota 77 Radar → Run workflow**

Horário de postagem: **07h–22h** (America/Sao_Paulo).
