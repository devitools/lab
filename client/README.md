# lab (client)

App desktop pra compartilhar pasta ou porta local em `*.devi.tools` via túnel WebSocket.

## Build

Pré-requisito: **Python 3.11+** instalado e no PATH (`py --version` no Windows funciona).

```bat
build.bat
```

Saída: `dist\lab.exe` (~15MB, single-file, sem dependência externa).

## Como usar

### Modo "Uma pasta"

1. Abrir o lab, marcar **"Uma pasta"**.
2. Escolher a pasta do projeto (com `index.html` dentro).
3. Clicar **Compartilhar**.
4. Copiar a URL retornada e mandar pro amigo.

O lab serve os arquivos direto do disco. Editou no editor, salvou, próxima request lê
a versão nova.

### Modo "Uma porta local"

1. Rodar o dev server local (`npm run dev`, `php -S`, etc).
2. Abrir o lab, marcar **"Uma porta local"**.
3. Informar a porta (ex: `5173` pro Vite).
4. Clicar **Compartilhar**.

URL fica ativa **enquanto o lab estiver rodando**. Fechar = derruba o túnel.

## Pegadinha do modo porta: dev server precisa aceitar Host externo

A maioria dos dev servers rejeita requests com Host externo por padrão.

**Vite** (`vite.config.js`):
```js
export default {
  server: {
    host: true,
    allowedHosts: ['.devi.tools'],
  },
}
```

**Create React App**:
```bash
HOST=0.0.0.0 DANGEROUSLY_DISABLE_HOST_CHECK=true npm start
```

**Next.js dev:** já aceita por padrão; rode `next dev -H 0.0.0.0`.
