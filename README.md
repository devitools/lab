# lab

Túnel reverso + publicação estática caseira pra `*.devi.tools`.

- **Documentação amigável** (pra mandar pra alguém usar): <https://lab.devi.tools>
- **Download do floofy.exe** (Windows): <https://github.com/devitools/lab/releases/download/latest/floofy.exe>

## Como funciona (visão simples)

A ideia é deixar fácil pegar um projeto que tá rodando só no seu PC e
gerar uma URL pública que qualquer um pode abrir no navegador.

Você abre o `floofy.exe` no Windows e escolhe um dos dois modos:

```
       MEU PC (Windows)                               SERVIDOR (devi.tools)
  ┌───────────────────────────┐                ┌──────────────────────────────┐
  │                           │                │                              │
  │     ┌───────────────┐     │                │      ┌────────────────┐      │
  │     │  floofy.exe   │     │                │      │  floofy-sun 🌞 │      │
  │     └───────┬───────┘     │                │      └────────┬───────┘      │
  │             │             │                │               │              │
  │   ┌─────────┴─────────┐   │                │               │              │
  │   │                   │   │                │               │              │
  │   ▼                   ▼   │                │               ▼              │
  │ [Publicar]      [Conectar]│                │       *.devi.tools           │
  │  pasta            porta   │                │     (URL pública             │
  │   │                 │     │                │      com HTTPS)              │
  │   │                 │     │                │               │              │
  │   ▼                 ▼     │                │               │              │
  │ dist/         localhost   │                │               │              │
  │ (build)       :5173       │                │               │              │
  │   │                 │     │                │               │              │
  └───┼─────────────────┼─────┘                └───────────────┼──────────────┘
      │                 │                                      │
      │ zip via HTTPS   │ túnel WebSocket                      │
      └────►────────────┴──────►──────────────────────────►────┘
              (uma vez)         (enquanto o floofy           o amigo abre
                                 estiver aberto)             <slug>.devi.tools

                                                                    ▼

                                                         ┌──────────────────┐
                                                         │  amigo da filha  │
                                                         │     (chrome)     │
                                                         └──────────────────┘
```

### Modo "Publicar pasta" (build estático)

1. Rodar o build do projeto: `npm run build` (Vite, React, Vue, etc.).
2. Abrir `floofy.exe`, aba **Publicar pasta**.
3. Escolher a pasta `dist/` (ou `build/`).
4. Opcional: digitar um nome amigável (ex: `meu-tcc`).
5. Clicar **Publicar**.
6. Copiar a URL que apareceu e mandar pro amigo.

A URL fica de pé pra sempre (até apagar). Funciona offline depois — o
PC da filha pode tá desligado e o site continua no ar.

Exemplo de URL: `https://meu-tcc-h7k2nq.devi.tools`

### Modo "Conectar porta" (dev server ao vivo)

1. Rodar o dev server: `npm run dev` (Vite costuma usar porta `5173`).
2. Abrir `floofy.exe`, aba **Conectar porta**.
3. Digitar a porta (ex: `5173`).
4. Opcional: nome amigável.
5. Clicar **Conectar**.
6. Copiar a URL e mandar pro amigo.

A URL fica ativa **enquanto o floofy.exe tiver aberto**. Fecha o app =
URL cai. Bom pra mostrar mudança ao vivo (a tela do amigo atualiza
junto com a sua quando você salva o código).

Exemplo de URL: `https://live-3yes4h.devi.tools`

### Qual modo escolher

|                                | Publicar pasta  | Conectar porta    |
|--------------------------------|-----------------|-------------------|
| Funciona depois de fechar o PC | ✅ sim          | ❌ não            |
| Mostra mudanças ao vivo (HMR)  | ❌ não          | ✅ sim            |
| Precisa rodar `npm run build`  | ✅ antes        | ❌ não            |
| Funciona com backend Java/PHP  | ❌ só estático  | ✅ se tiver porta |
| Bom pra entregar trabalho      | ✅              | ⚠️ instável        |
| Bom pra demonstração rápida    | ⚠️ exige build  | ✅                |

### Pegadinha importante: dev server precisa aceitar Host externo

O Vite (e quase todo dev server) rejeita conexões com Host diferente de
`localhost` por padrão. Se ao abrir a URL aparecer "Blocked request",
ajustar o `vite.config.js`:

```js
export default {
  server: {
    host: true,
    allowedHosts: ['.devi.tools'],
  },
}
```

Outros: ver [client/README.md](client/README.md).

---

## Componentes do projeto

- [`server/`](server/) — serviço Go (`floofy-sun`) que roda na VPS
  `devi.tools`. Recebe uploads, mantém túneis WebSocket reversos,
  roteia `<slug>.devi.tools` pro destino certo.
- [`client/`](client/) — app Windows (Python + Tkinter empacotado em
  `.exe`) com as duas abas. Build via `client/build.bat`.
- [`docs/`](docs/) — landing pública em <https://lab.devi.tools>
  (GitHub Pages, custom domain via CNAME).

## Decisões de arquitetura

| | |
|---|---|
| Subdomínio raiz | `*.devi.tools` (regex VIRTUAL_HOST, match exato vence pra subdomínios já cadastrados) |
| Cert | Wildcard `*.devi.tools` via certbot DNS-01 (DO API), renova semanal via cron |
| Auth | Slug aleatório `<friendly>-<rand6>` ~30 bits (sem token) |
| Storage estático | `/home/heimdall/floofy/sites/<slug>/` |
| GC estático | 30 dias sem acesso → registry remove |
| Admin endpoint | `floofy.devi.tools` (`/publish`, `/tunnel`, `/health`) |
