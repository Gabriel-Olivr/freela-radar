# Radar de Freela

Procura vagas `[Hiring]` no Reddit que combinam com Python, C#, SQL e dados,
avisa no **WhatsApp** e mostra tudo num painel no **GitHub Pages**.

```
seu PC (radar.py)  ──►  WhatsApp (CallMeBot)
        │
        └─ git push docs/vagas.json ──►  GitHub Pages (docs/index.html)
```

O robô roda no seu PC porque o GitHub Pages só serve páginas (não executa
Python) e o Reddit costuma recusar pedidos vindos do GitHub Actions.
Com o PC desligado, o painel continua no ar, mas sem vagas novas.

## Configurar (uma vez)

1. **Repositório**: crie `freela-radar` **público** no GitHub (Pages grátis exige
   repositório público). Só vão para lá a página e a lista de vagas, que já são
   posts públicos do Reddit. O `.env` com as suas chaves fica fora (`.gitignore`).
2. **Pages**: Settings → Pages → *Deploy from a branch* → `main` / `docs`.
   O painel fica em `https://gabriel-olivr.github.io/freela-radar/`.
3. **WhatsApp (CallMeBot, grátis)**: confira o número atual em callmebot.com,
   salve nos contatos e mande pelo WhatsApp: `I allow callmebot to send me messages`.
   A resposta traz a sua *apikey*.
4. **`.env`**: copie `.env.example` para `.env` e preencha telefone (+55…), apikey e
   o endereço do painel.
5. **Teste**: `python radar.py --teste` → deve chegar uma mensagem no WhatsApp.
6. **Ligar**: `python radar.py` (ou dois cliques em `iniciar_radar.bat`).
   Para ligar junto com o Windows: Win+R → `shell:startup` → cole um atalho do `.bat`.
7. **iPhone**: abra o painel no Safari → Compartilhar → *Adicionar à Tela de Início*.

Precisa do Git instalado e logado no GitHub no PC (o `git push` é feito pelo radar).

## Ajustar

Tudo em `config.json`: subreddits, palavras-chave, termos que excluem a vaga,
sinais de golpe, intervalo (padrão 3 min) e quantas mensagens por ciclo.
Vagas com cara de golpe aparecem no painel marcadas, mas não vão para o WhatsApp
(mude `avisar_golpe_no_whatsapp` para `true` se quiser).

Opções: `--sem-push` (não publica), `--uma-vez` (um ciclo), `--historico`
(na 1ª vez também avisa o que já estava no feed), `--arquivo feed.xml` (teste offline).

Telegram também funciona: preencha `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`.
