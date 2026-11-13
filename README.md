# TV INGÁ STUDIO — Piloto técnico v0.1

Protótipo de **central editorial** com **17 programas** da TV Ingá, painel navegável, padrões básicos de legenda por programa, prévia local, seleção manual de cortes, fila de aprovação e um **backend Python opcional** de transcrição, sugestões e renderização de MP4 legendado.

> **Escopo real:** beta técnico / prova de conceito. Não é um produto pronto para múltiplos editores ou para operação de uma emissora. A versão publicada no GitHub Pages é um painel estático que **não** transcreve nem renderiza vídeos sozinha. A parte de IA requer o backend instalado e um arquivo original autorizado.

## Organização do repositório

```text
tv-inga-studio/
├── docs/                         # PASTA PUBLICADA NO GITHUB PAGES
│   ├── index.html                # Interface HTML
│   ├── .nojekyll
│   ├── assets/
│   │   ├── style.css             # Estilo responsivo
│   │   └── app.js                # Navegação e interatividade
│   └── data/
│       ├── programs.json         # 17 links cadastrados na ordem recebida
│       └── presets.json          # Espelhos base por programa
├── backend/
│   ├── main.py                   # API FastAPI e upload
│   ├── pipeline.py               # FFmpeg, Whisper e legendas ASS
│   ├── requirements.txt
│   └── .env.example
├── templates/
│   └── espelhos-base.json        # Backup dos presets iniciais
├── tests/
│   └── test_pipeline.py          # Testes unitários
├── .gitignore
└── README.md
```

## 1 — Colocar a interface no GitHub Pages

1. Crie um repositório GitHub, por exemplo `tv-inga-studio`.
2. Envie **todos os arquivos do projeto**, preservando as pastas (`docs`, `backend`, `templates`, `tests`). Não envie a pasta compactada sem extrair.
3. No repositório, abra **Settings → Pages**.
4. Em **Build and deployment**, selecione **Deploy from a branch**, branch `main` e pasta `/docs`. Salve.
5. Aguarde a publicação indicada pelo próprio GitHub. O endereço terá uma estrutura semelhante a `https://SEU-USUARIO.github.io/tv-inga-studio/` (é um **exemplo**, não é um link já publicado).
6. Navegue em **Visão geral → Programas → Novo projeto → Espelhos visuais → Fila editorial**.

**O que funciona só com GitHub Pages:** seleção e busca de 17 programas, links externos, padrão visual editável, carregamento/visualização de vídeo no browser, marcação de início/fim de trechos, fila de revisão, aprovação local e exportação CSV da fila. Informações são gravadas em `localStorage` neste navegador; **não são compartilhadas entre computadores**. A interface não faz upload de vídeos por conta própria.

**Atenção à privacidade:** mesmo com repositório privado, a publicação no GitHub Pages pode ficar disponível ao público dependendo da configuração/plano. Este beta usa apenas links públicos e dados de exemplo. Não coloque projetos ou vídeos internos da emissora em `docs/`.

## 2 — Rodar a interface localmente (sem IA)

Na pasta raiz do repositório:

```bash
python3 -m http.server 8080 --directory docs
```

Abra `http://127.0.0.1:8080`. Evite abrir o arquivo por `file://`, pois isso pode bloquear o carregamento de JSON no navegador.

## 3 — Rodar o backend Python com transcrição e renderização

### Pré-requisitos

- Python 3.10+ e `pip`.
- `ffmpeg` e `ffprobe`, com suporte a `subtitles/libass`, instalados no sistema.
  - macOS com Homebrew: `brew install ffmpeg`
  - Linux Debian/Ubuntu: `sudo apt install ffmpeg`
- Internet na primeira execução para baixar os pesos do modelo `faster-whisper` (padrão: `base`).
- Vídeos com uso autorizado pela emissora. O sistema não extrai vídeos automaticamente do site da TV.

No terminal, a partir da pasta raiz:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

No Windows, ative o virtualenv com `.venv\\Scripts\\activate`.

Abra **http://127.0.0.1:8000** no mesmo computador. O frontend já está sendo servido pelo próprio Python, então a API é detectada automaticamente. Se você abrir a interface em outro domínio, configure em **Configurações** a URL HTTPS da API e, do lado do servidor, ajuste `ALLOWED_ORIGINS` para permitir exclusivamente o domínio autorizado.

**Segurança:** a API de demonstração não possui autenticação, permissões, gestão de equipe ou proteção anti-abuso. Inicie apenas em `127.0.0.1`; **não exponha na internet**, nem use host `0.0.0.0` como atalho, até que esses recursos existam.

### Fluxo com IA

1. Abra **Novo projeto**.
2. Escolha um dos programas.
3. Selecione um MP4/MOV/WebM/MKV autorizado.
4. Clique em **Gerar até 10 sugestões com IA**.
5. O backend extrai o áudio, transcreve com Whisper e **seleciona trechos com heurísticas simples** (duração, densidade de fala, expressões e sinais de pergunta). **Não existe ainda uma IA treinada para identificar os cortes de maior potencial de audiência.**
6. Revise os títulos e os tempos na interface. Os timestamps exibidos são sugestões; é responsabilidade do editor verificar contexto e precisão.
7. Clique em **Exportar MP4** numa sugestão; o backend aplica legendas ASS com cores/posição/animação base do espelho do programa e renderiza um **MP4 vertical de 720×1280** via FFmpeg.
8. Adicione o corte à fila para revisão e, se necessário, baixe o MP4 renderizado.

**Limitações do backend:** sem processamento paralelo controlado, sem persistência de jobs após reinicialização, sem banco de dados, sem fila distribuída, sem login e sem edição detalhada de timeline. O pipeline pode demorar em vídeos longos; o Whisper pode cometer erros. Sugestões automáticas podem ser menos de 10 quando não há duração ou fala suficientes.

### Como mudar os espelhos

Na interface, abra **Espelhos visuais** e escolha o programa. Personalize fonte, cores, posição e animação (fade/pop); salve no navegador. Na exportação de um MP4, a configuração atual é enviada ao backend.

Estes são **presets básicos**, não a reprodução fiel de um vídeo que você editou manualmente. Para implantar seu conceito de espelhamento com motion graphics avançado, os próximos passos são: receber o vídeo editado e **arquivos de projeto e assets**, mapear o design e suas regras, construir templates determinísticos de animação, inserir imagens de apoio licenciadas e validar cada elemento.

### Erros comuns

- `FFmpeg não encontrado`: instale FFmpeg e verifique `ffmpeg -version`.
- `faster-whisper não instalado`: instale as dependências do backend no ambiente correto.
- `transcrição falhou`: verifique o formato de vídeo, áudio, conexão para baixar o modelo e logs do terminal.
- `servidor desconectado` no GitHub Pages: esperado até hospedar a API em servidor HTTPS separado ou acessar `127.0.0.1:8000` localmente.
- `falha de CORS`: permita apenas a origem do frontend via `ALLOWED_ORIGINS`; não use `*` em ambiente com dados privados.
- O site do programa não reproduz vídeo na plataforma: os links cadastrados são **páginas externas**, não MP4 nem endpoints de transmissão.

## 4 — Testes

```bash
python3 -m unittest discover -s tests -v
```

O teste de integração da API não baixa o Whisper nem realiza processamento pesado automaticamente. Para validar o render, use um clipe de teste autorizado e FFmpeg.

## Planejamento das próximas versões

- **v0.2:** armazenamento centralizado de projetos, revisão fina dos trechos e login para equipe.
- **v0.3:** espelhos visuais avançados (templates derivados dos arquivos editáveis), imagens de apoio com licença e efeitos específicos por programa.
- **v0.4:** fila assíncrona de renderização, indicadores de economia de tempo e auditoria editorial.
- **v1.0 (condicionada à validação):** publicação via APIs oficiais e autorizações específicas de cada plataforma, com supervisão humana.

## Fonte da grade

Os 17 endereços foram informados pelo responsável pelo projeto e permanecem na ordem original. A URL que continha `podju/https://...justica-da-saude/` foi separada em **PodJu** e **Justiça da Saúde**. Alguns links não puderam ser confirmados por acesso automatizado e devem ser conferidos manualmente antes de uso operacional.

## Licenciamento de conteúdos e projetos de código aberto

Este projeto foi escrito como estrutura própria, sem copiar código de projetos de terceiros. Qualquer futura incorporação de código do GitHub precisa de verificação de licença e atribuição. Faça o mesmo para trilhas, fontes, logos e vídeos usados nas renderizações.
