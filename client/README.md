# floofy (client)

App Windows pra publicar projetos locais em `*.lab.devi.tools`.

## Build

Pré-requisito: **Python 3.11+** instalado e no PATH (`py --version` no Windows funciona).

```bat
build.bat
```

Saída: `dist\floofy.exe` (~15MB, single-file, sem dependência externa).

## Como usar

### Modo "Publicar pasta"
1. Rodar o build do projeto (`npm run build`, `vite build`, etc.).
2. Abrir o floofy, aba **Publicar pasta**.
3. Escolher a pasta `dist/` gerada.
4. Opcional: digitar um nome amigável (ex: `meu-tcc`).
5. Clicar **Publicar**.
6. Copiar a URL retornada e mandar pro amigo.

Build estático fica salvo em `<slug>.lab.devi.tools` por 30 dias (renova quando acessado).

### Modo "Conectar porta"
1. Rodar o dev server local (`npm run dev`, etc.).
2. Abrir o floofy, aba **Conectar porta**.
3. Informar a porta (ex: `5173` pro Vite).
4. Opcional: nome amigável.
5. Clicar **Conectar**.
6. Copiar a URL e mandar pro amigo.

URL fica ativa **enquanto o floofy estiver rodando**. Fechar = derruba o túnel.

## Pegadinha: dev server precisa aceitar Host externo

A maioria dos dev servers rejeita requests com Host externo por padrão.

**Vite** (`vite.config.js`):
```js
export default {
  server: {
    host: true,
    allowedHosts: ['.lab.devi.tools'],
  },
}
```

**Create React App**:
```bash
HOST=0.0.0.0 DANGEROUSLY_DISABLE_HOST_CHECK=true npm start
```

**Next.js dev:** já aceita por padrão; rode `next dev -H 0.0.0.0`.
