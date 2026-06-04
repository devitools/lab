# lab

Túnel reverso + publicação estática caseira pra `*.lab.devi.tools`.

Dois componentes:

- `server/` — serviço Go (`floofy-sun`) que roda na VPS `devi.tools`. Recebe uploads de builds estáticos, mantém tunneis WebSocket reversos, roteia `<slug>.lab.devi.tools` pro destino certo.
- `client/` — app Windows (Python + Tkinter empacotado em `.exe`) com dois modos: **publicar pasta** (upload de `dist/`) e **conectar porta** (túnel ao vivo pro `localhost:<porta>`).

Veja [server/README.md](server/README.md) e [client/README.md](client/README.md) para detalhes.

## Decisões base

| | |
|---|---|
| Subdomínio | `*.lab.devi.tools` |
| Cert | Wildcard via DNS-01 (DO API), renova mensal via cron |
| Auth | Slug aleatório `<friendly>-<rand12>` ~60 bits (sem token) |
| Storage | `/home/heimdall/floofy/sites/<slug>/` |
