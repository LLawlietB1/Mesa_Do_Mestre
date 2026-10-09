# Mesa do Mestre

Aplicação web para mestres de RPG de mesa organizarem campanhas, jogadores, personagens, **XP manual**, notas privadas, diário de sessões, NPCs, missões e inventário — e **enviarem dados da campanha aos jogadores por WhatsApp/SMS**. Python (Flask + SQLAlchemy), Postgres (Neon) em produção, SQLite em desenvolvimento, hospedável na **Vercel**.

> **Multiusuário.** Cada pessoa cria a própria conta (login e senha) e só enxerga os **próprios** dados. Veja [SECURITY.md](SECURITY.md).

## Recursos

- Login, cadastro (com código de convite), recuperação de senha por palavra-chave (sem e-mail), bloqueio após tentativas erradas, sair de todos os dispositivos e exclusão de conta.
- Várias campanhas independentes; jogadores podem participar de várias; personagens com campos opcionais e extensíveis.
- **Barra de XP (0–100%)** com ±5/±10, valor livre, definir, zerar, completar, histórico, alteração coletiva transacional e novo ciclo explícito (o nível nunca sobe sozinho).
- Notas privadas, diário de sessões e linha do tempo, NPCs e relações, missões com objetivos e histórico, inventário.
- **Mensagens aos jogadores** (ficha/XP, inventário, próxima sessão, resumo, missões ou texto livre): você revisa/edita e envia por link de **WhatsApp** ou **SMS** (abre no seu celular/PC, sem custo) ou, opcionalmente, direto pelo servidor via Twilio.
- Backup e restauração **por conta** (JSON + imagens em .zip), transacional.
- Interface responsiva com animações; imagens recodificadas e guardadas no banco.

## Rodar localmente (Windows / PowerShell)

1. Instale o Python 3.12+ (marque *Add python.exe to PATH*).
2. Na pasta do projeto:
   ```powershell
   .\setup.ps1 -Run
   ```
   (Se o PowerShell bloquear: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.) Isso cria o `.venv`, instala as dependências, cria o `.env`, cria o banco SQLite local e inicia em **http://127.0.0.1:5000**.
3. Abra `/cadastro` e crie sua conta (em desenvolvimento o cadastro é livre).

Manual:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
$env:FLASK_APP = "run.py"
flask db upgrade
python run.py
```

Testes: `pytest` (usa SQLite em memória e **nunca** toca nos seus dados). Para rodar a suíte contra um Postgres de teste: defina `TEST_DATABASE_URL` (⚠ o banco indicado é **apagado e recriado**; use um banco/branch descartável).

## Deploy na Vercel (com Neon Postgres)

Mesmo caminho do Professor Helper.

1. **Repositório:** suba o projeto para o GitHub (o `.gitignore` já exclui `.env`, `.venv` e `instance/`).
2. **Projeto na Vercel:** *Add New → Project* → importe o repositório. Framework: *Flask* (detectado). O `pyproject.toml` indica o ponto de entrada (`[tool.vercel] entrypoint = "run:app"`) e as dependências; não há `vercel.json`. Se faltar variável obrigatória, o site abre uma página explicando o que falta.
3. **Banco:** aba *Storage* (ou Marketplace) → **Neon Postgres** → conectar ao projeto. Isso cria `DATABASE_URL`/`POSTGRES_URL` automaticamente (o app aceita as duas).
4. **Variáveis de ambiente** (Settings → Environment Variables, ambiente *Production*):
   | Variável | Valor |
   |---|---|
   | `SECRET_KEY` | **obrigatória** — `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `INVITE_CODE` | **recomendada** — código que você passa aos amigos (sem ele, o cadastro fica fechado em produção) |
   | `USER_IMAGE_QUOTA_MB` | opcional (padrão 3) |
   | `RESEND_API_KEY`, `ADMIN_EMAIL` | para o e-mail de pedido de liberação de imagens (ver abaixo) |
   | `TWILIO_*`, `MESSAGES_PER_DAY` | opcionais — só para envio direto (ver abaixo) |
5. **Criar as tabelas** (uma vez, e a cada migration nova), do seu computador, apontando para o Neon com a conexão **direta** (`POSTGRES_URL_NON_POOLING` do painel do Neon/Vercel):
   ```powershell
   $env:DATABASE_URL = "<conexão direta do Neon>"
   $env:FLASK_APP = "run.py"
   .\.venv\Scripts\flask.exe db upgrade
   ```
6. **Deploy:** *Deploy* (ou push na branch principal). Abra a URL, vá em `/cadastro` e use o `INVITE_CODE` para criar sua conta e depois passe o código aos amigos.

Pontos de atenção na Vercel:
- O disco é efêmero: por isso as imagens ficam **no banco** (tabela `file_assets`, com cota por conta) e o backup é um download.
- Corpo de requisição/resposta limitado a ~4,5 MB: vale para upload de imagem e para backups (mantenha a cota baixa).
- O plano gratuito do Neon tem 0,5 GB: mais que suficiente para algumas mesas.

## Liberação do envio de imagens (e-mail ao administrador)

Mesmo esquema do Professor Helper: para controlar o armazenamento, **cada conta nova começa sem poder enviar imagens**.

1. A pessoa abre *Minha conta → Pedir liberação de imagens*. O sistema registra o pedido e **envia um e-mail ao administrador** (Resend).
2. Você abre o link do e-mail (**/admin/imagens**) e clica em **Liberar** — ou roda `flask approve-images email@da-pessoa.com`.
3. Os campos de imagem (retrato, capa, NPC) ficam desabilitados, com explicação, até a liberação. Admins sempre podem enviar.

Configuração (Vercel → Environment Variables; pode reaproveitar a mesma conta Resend do Professor Helper):
`RESEND_API_KEY`, `ADMIN_EMAIL` (sem domínio verificado o Resend só entrega para o e-mail da própria conta Resend), `RESEND_FROM` (opcional).
Se o e-mail falhar, o pedido fica registrado e aparece em **Administração**.

**Tornar a sua conta administradora** (uma vez, do seu PC, com `DATABASE_URL` apontando para o Neon): `flask make-admin seu@email.com`. Isso libera o menu *Administração*.

## Desempenho

- Cada página faz poucas consultas (orçamento verificado por teste: nenhuma página cresce com a quantidade de dados) e a conexão com o Postgres é reaproveitada entre requisições.
- CSS/JS têm hash na URL e cache de 1 ano; o cabeçalho `Server-Timing` (DevTools → Network → Timing) mostra o tempo e o nº de consultas de cada requisição.
- Dica importante: deixe a **região da função na Vercel igual à região do Neon** (Settings → Functions → Region). Banco e função em continentes diferentes custam dezenas de ms por consulta.

## Mensagens: WhatsApp e SMS

1. No cadastro do jogador, informe o **telefone** (com DDD; o `+55` é completado sozinho) e marque o **consentimento** de que ele aceita receber mensagens.
2. Em **Mensagens**, escolha o tipo de dado, os destinatários e gere a prévia. Cada texto é editável.
3. Botões:
   - **WhatsApp** → abre `wa.me` com a mensagem pronta no *seu* WhatsApp (o seu próprio número; você só aperta enviar).
   - **SMS** → abre o app de SMS do aparelho com a mensagem pronta.
   - **Copiar texto**.
   - **Enviar pelo servidor** (opcional, ver abaixo).

As mensagens só usam **dados públicos**; notas privadas, segredos de NPC e observações do mestre nunca entram no texto (há teste automatizado para isso).

### Envio direto pelo servidor (opcional, Twilio)

Para disparar sem abrir o aplicativo: crie uma conta no [Twilio](https://www.twilio.com/), configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM` (número para SMS) e/ou `TWILIO_WHATSAPP_FROM` (sandbox do Twilio WhatsApp para testes; para usar o **seu próprio número** como remetente é preciso registrá-lo como *WhatsApp sender* no Twilio). Como isso consome crédito seu, **cada conta precisa ser liberada manualmente**:

```powershell
flask grant-messaging amigo@exemplo.com            # libera
flask grant-messaging amigo@exemplo.com --revoke   # revoga
flask list-users
```
(Rode apontando `DATABASE_URL` para o Neon.) Há limite diário por conta (`MESSAGES_PER_DAY`) e um registro de envios (sem o texto da mensagem).

## Contas e segurança

- Recuperação de senha: **e-mail + palavra-chave** definida no cadastro (não há e-mail). Sem a palavra-chave não há como recuperar — troque-a em *Minha conta*.
- Cadastro: use `INVITE_CODE`. Cada conta é isolada das demais.
- Backup (menu *Backup*): baixe periodicamente. A restauração substitui **somente os seus dados**, em uma transação (se falhar, nada muda).

## Estrutura

```
run.py               entrada (local e Vercel: `run:app`)    pyproject.toml  dependências + entrypoint da Vercel
app/                 fábrica, models, services, forms, routes, templates, static
  services/auth.py        Argon2id, sessões, bloqueio, recuperação
  services/ownership.py   isolamento por usuário (get_or_404 verifica o dono)
  services/backup.py      backup/restauração por usuário
  services/messaging.py   textos, links WhatsApp/SMS, Twilio
  services/uploads.py     validação/recodificação de imagens (Pillow) no banco
migrations/          Alembic (Postgres e SQLite)
tests/               pytest (193+ testes, incluindo varredura de IDOR)
```

Novo módulo: `models/x.py`, `forms/x.py`, `routes/x.py` (registrar em `routes/__init__.py`), migration (`flask db migrate -m "..."`, revisar, `flask db upgrade`). **Regra de ouro:** todo registro novo deve pertencer a um usuário (direto ou via campanha) e as rotas devem carregá-lo com `get_or_404` (que confere o dono); some um teste em `tests/test_isolation.py`.

## O que mudou em relação à versão local (mesmas ideias do Professor Helper)

SQLite+disco → Postgres+imagens no banco; app de uma pessoa → multiusuário com login; backup do arquivo inteiro → backup **escopado por usuário** (um backup do banco todo vazaria dados de todos); cabeçalhos de segurança e cookies `Secure` em produção; configuração por variáveis de ambiente.

## Limitações conhecidas

- Sem recuperação por e-mail (por escolha, como no Professor Helper).
- Limite por IP no login não existe (o bloqueio é por conta); o `INVITE_CODE` evita cadastros abertos.
- Imagens: cota pequena por causa do limite de corpo da Vercel.
- O suporte a Postgres foi validado pelo DDL gerado e pela suíte em SQLite; rode a suíte com `TEST_DATABASE_URL` num banco descartável do Neon para confirmar no seu ambiente.
