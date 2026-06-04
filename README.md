# lab

Túnel reverso + publicação estática caseira pra `*.devi.tools`.

- **Documentação amigável** (pra mandar pra alguém usar): <https://lab.devi.tools>
- **Download lab** — [Windows](https://github.com/devitools/lab/releases/download/latest/lab.exe) · [macOS](https://github.com/devitools/lab/releases/download/latest/lab-macos.zip)

## Como funciona (visão simples)

A ideia é deixar fácil pegar um projeto que tá rodando só no seu PC e
gerar uma URL pública que qualquer um pode abrir no navegador.

Você abre o `lab.exe` no Windows e escolhe um dos dois modos:

```
       MEU COMPUTADOR                              SERVIDOR (devi.tools)
  ┌─────────────────────────┐               ┌────────────────────────────┐
  │                         │               │                            │
  │    ┌───────────────┐    │               │     ┌──────────────────┐   │
  │    │      lab      │    │               │     │     lab 🌞       │   │
  │    └───────┬───────┘    │               │     └─────────┬────────┘   │
  │            │            │               │               │            │
  │   ┌────────┴────────┐   │               │               │            │
  │   │                 │   │               │               │            │
  │   ▼                 ▼   │               │               ▼            │
  │ [Publicar]   [Conectar] │               │         *.devi.tools       │
  │   │                 │   │               │       (URL pública,        │
  │   ▼                 ▼   │               │        HTTPS automático)   │
  │ pasta         localhost │               │               │            │
  │ do site         :5500   │               │               │            │
  │   │                 │   │               │               │            │
  └───┼─────────────────┼───┘               └───────────────┼────────────┘
      │                 │                                   │
      │  zip via HTTPS  │   túnel WebSocket persistente     │
      └─►───────────────┴──────►─────────────────────►──────┘
          (uma vez)         (enquanto o lab              o amigo abre
                             estiver aberto)              <slug>.devi.tools
                                                                ▼
                                                       ┌──────────────────┐
                                                       │   amigo dela     │
                                                       │     (chrome)     │
                                                       └──────────────────┘
```

### Modo "Publicar pasta" (build estático)

1. Rodar o build do projeto: `npm run build` (Vite, React, Vue, etc.).
2. Abrir `lab.exe`, aba **Publicar pasta**.
3. Escolher a pasta `dist/` (ou `build/`).
4. Opcional: digitar um nome amigável (ex: `meu-tcc`).
5. Clicar **Publicar**.
6. Copiar a URL que apareceu e mandar pro amigo.

A URL fica de pé pra sempre (até apagar). Funciona offline depois — o
PC da filha pode tá desligado e o site continua no ar.

Exemplo de URL: `https://meu-tcc-h7k2nq.devi.tools`

### Modo "Conectar porta" (dev server ao vivo)

1. Rodar o dev server: `npm run dev` (Vite costuma usar porta `5173`).
2. Abrir `lab.exe`, aba **Conectar porta**.
3. Digitar a porta (ex: `5173`).
4. Opcional: nome amigável.
5. Clicar **Conectar**.
6. Copiar a URL e mandar pro amigo.

A URL fica ativa **enquanto o lab.exe tiver aberto**. Fecha o app =
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

- [`server/`](server/) — serviço Go (`lab`) que roda na VPS
  `devi.tools`. Recebe uploads, mantém túneis WebSocket reversos,
  roteia `<slug>.devi.tools` pro destino certo.
- [`client/`](client/) — app Windows (Python + Tkinter empacotado em
  `.exe`) com as duas abas. Build via `client/build.bat`.
- [`docs/`](docs/) — landing pública em <https://lab.devi.tools>
  (embutida no binário do server via `go:embed` no build).

## Decisões de arquitetura

| | |
|---|---|
| Subdomínio raiz | `*.devi.tools` (regex VIRTUAL_HOST, match exato vence pra subdomínios já cadastrados) |
| Cert | Wildcard `*.devi.tools` via certbot DNS-01 (DO API), renova semanal via cron |
| Auth | Slug aleatório `<friendly>-<rand6>` ~30 bits (sem token) |
| Storage estático | `/projects/lab.devi.tools/app/server/sites/<slug>/` |
| GC estático | 30 dias sem acesso → registry remove |
| Admin endpoint | `lab.devi.tools` (`/publish`, `/tunnel`, `/health`) |
