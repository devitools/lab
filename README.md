# lab

Túnel reverso caseiro pra `*.devi.tools`. Compartilhar projetos locais em URL pública sem ngrok, sem SSH, sem cadastro.

- **Documentação amigável**: <https://lab.devi.tools>
- **Download** — [Windows](https://github.com/devitools/lab/releases/download/latest/lab.exe) · [macOS](https://github.com/devitools/lab/releases/download/latest/lab-macos.zip) · [Linux (AppImage)](https://github.com/devitools/lab/releases/download/latest/lab-linux.AppImage)

## Como funciona

A ideia é deixar fácil pegar um projeto que tá rodando só no seu PC e
gerar uma URL pública que qualquer um pode abrir no navegador.

Você abre o `lab.exe` (ou `lab.app`) e escolhe entre dois modos:

```
       MEU COMPUTADOR                              SERVIDOR (devi.tools)
  ┌─────────────────────────┐               ┌────────────────────────────┐
  │    ┌───────────────┐    │               │     ┌──────────────────┐   │
  │    │      lab      │    │               │     │       lab        │   │
  │    └───────┬───────┘    │               │     └─────────┬────────┘   │
  │            │            │               │               ▼            │
  │   ┌────────┴────────┐   │               │         *.devi.tools       │
  │   ▼                 ▼   │               │       (URL pública,        │
  │ [Pasta]       [Porta]   │               │        HTTPS automático)   │
  │   │                 │   │               │               │            │
  │   ▼                 ▼   │               │               │            │
  │ disco         localhost │               │               │            │
  │ local           :5173   │               │               │            │
  └───┴──────┬──────────┴───┘               └───────────────┼────────────┘
             │                                              │
             │              túnel WebSocket persistente     │
             └──────►──────────────────────►────────────────┘
                       (enquanto o lab              o amigo abre
                        estiver aberto)              <slug>.devi.tools
                                                                ▼
                                                          chrome do amigo
```

### Modo "Compartilhar pasta"

Pra HTML estático ou build pronto.

1. Abrir o lab, marcar **"Uma pasta"**.
2. Escolher a pasta com seu `index.html`.
3. Clicar **Compartilhar**.
4. Copiar a URL e mandar pro amigo.

O lab serve os arquivos direto do disco via WebSocket. Editou, salvou, próxima request lê
a versão nova. Sem dev server externo, sem WebStorm, sem `Allowed Hosts`.

### Modo "Compartilhar porta"

Pra dev server ao vivo (Vite, Next, Java, PHP, etc).

1. Subir o servidor local: `npm run dev`, `php -S`, etc.
2. No lab marcar **"Uma porta local"**.
3. Digitar a porta (Vite 5173, Next 3000…).
4. Clicar **Compartilhar**.

HMR funciona — o amigo vê suas mudanças ao vivo.

### Vida útil

Em ambos os modos, a URL fica de pé **enquanto o lab tiver aberto**. Fecha = cai. Nada
fica armazenado no servidor. Pra entregar trabalho que precisa sobreviver com o PC
desligado, use GitHub Pages, Netlify ou Vercel.

### Pegadinha do modo porta: dev server precisa aceitar Host externo

O Vite (e quase todo dev server) rejeita conexões com Host diferente de `localhost` por
padrão. Se ao abrir a URL aparecer "Blocked request", ajustar o `vite.config.js`:

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

## Componentes

- [`server/`](server/) — serviço Go (`lab`) que roda na VPS `devi.tools`. Aceita conexões
  WebSocket de clientes e roteia `<slug>.devi.tools` pro túnel certo.
- [`client/`](client/) — app desktop (Python + Tkinter empacotado em `.exe` / `.app`) que
  abre o túnel e serve a pasta ou proxya a porta local.
- [`docs/`](docs/) — landing pública em <https://lab.devi.tools> (embutida no binário do
  server via `go:embed` no build).

## Decisões de arquitetura

| | |
|---|---|
| Subdomínio raiz | `*.devi.tools` (regex `VIRTUAL_HOST`, match exato vence pra subdomínios já cadastrados) |
| Cert | Wildcard `*.devi.tools` via certbot DNS-01 (DO API), renova semanal via cron |
| Auth | Slug aleatório `<friendly>-<rand6>` ~30 bits (sem token) |
| Protocolo | Envelope JSON sobre WebSocket: req/resp com base64 body |
| Estado no servidor | Só o map slug → conn WS na memória. Nada em disco, nada persiste |
| Admin endpoint | `lab.devi.tools` (`/tunnel`, `/health`) |
