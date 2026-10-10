# Mesa do Mestre

Aplicação web para mestres de RPG de mesa organizarem campanhas, jogadores, personagens, **XP manual**, notas privadas, diário de sessões, NPCs, missões e inventário — e **enviarem dados da campanha aos jogadores por WhatsApp/SMS**.

Python (Flask + SQLAlchemy). **Roda no seu próprio computador**, com banco SQLite local, sem nuvem e sem nenhum custo.

> **Multiusuário.** Cada pessoa cria a própria conta (login e senha) e só enxerga os **próprios** dados. Veja [SECURITY.md](SECURITY.md).

## Começo rápido (Windows)

Pré-requisito: **Python 3.12 ou superior** ([python.org](https://www.python.org/downloads/); marque *Add python.exe to PATH* na instalação). Nada mais.

1. Baixe/clone o repositório.
2. Dê dois cliques em **`local\iniciar.bat`**.
   - Na primeira vez ele cria o ambiente virtual, instala as dependências e cria o banco (leva alguns minutos).
3. O navegador abre em **http://127.0.0.1:5000/cadastro**. Crie sua conta: **a primeira conta criada vira administradora** (já pode enviar imagens).
4. Para encerrar, feche a janela preta. Nas próximas vezes, basta abrir o `iniciar.bat` de novo e entrar em http://127.0.0.1:5000.

Se o Windows bloquear o script, rode no PowerShell, dentro da pasta do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File .\local\iniciar.ps1
```

Para usar outra porta: `$env:PORT = "5055"` antes de rodar o comando acima. Mais detalhes em [local/LEIA-ME.md](local/LEIA-ME.md).

### Seus dados

- Ficam em `local\dados\` (banco `mesa.sqlite3`, chave de sessão `.secret_key`). Essa pasta **não vai para o GitHub**.
- **Backup:** feche o app e copie a pasta `local\dados` — ou use o menu *Backup* dentro do app (baixa um `.zip` com seus dados e imagens).
- **Recomeçar do zero:** feche o app e apague a pasta `local\dados`.

### Outros sistemas (Linux/macOS) ou sem o `.bat`

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=run.py
flask db upgrade        # cria o banco SQLite em instance/mesa.sqlite3
python run.py           # http://127.0.0.1:5000  → crie sua conta em /cadastro
```

No Windows/PowerShell o equivalente é `.\setup.ps1 -Run` (cria `.venv`, instala dependências de desenvolvimento, cria o `.env`, o banco e inicia). Esse caminho guarda o banco em `instance\` (e não em `local\dados`).

## Recursos

- Login, cadastro, recuperação de senha por palavra-chave (sem e-mail), bloqueio após tentativas erradas, sair de todos os dispositivos e exclusão de conta.
- Várias campanhas independentes; jogadores podem participar de várias; personagens com campos opcionais e extensíveis.
- **Barra de XP (0–100%)** com ±5/±10, valor livre, definir, zerar, completar, histórico, alteração coletiva transacional e novo ciclo explícito (o nível nunca sobe sozinho).
- Notas privadas, diário de sessões e linha do tempo, NPCs e relações, missões com objetivos e histórico, inventário.
- **Mensagens aos jogadores** (ficha/XP, inventário, próxima sessão, resumo, missões ou texto livre): você revisa/edita e envia por link de **WhatsApp** ou **SMS** (abre no seu celular/PC, sem custo) ou, opcionalmente, direto pelo servidor via Twilio.
- Backup e restauração **por conta** (JSON + imagens em .zip), transacional.
- Interface responsiva; imagens recodificadas (Pillow) e guardadas no banco.

## Quem pode usar

Por padrão o servidor escuta **só em `127.0.0.1`**: apenas o seu computador acessa. Várias contas podem existir na mesma instalação (cada uma isolada das demais), mas outras pessoas só conseguem usar se você expuser o app na rede ou na internet por conta própria — algo que este projeto não configura nem recomenda sem cuidados (use `MESA_ENV=production`, `SECRET_KEY`, `INVITE_CODE` e HTTPS atrás de um proxy reverso, com `TRUST_PROXY=1`).

## Configuração (opcional)

O `iniciar.bat` não precisa de configuração. Para quem roda `python run.py`/`flask` diretamente, copie `.env.example` para `.env`; todas as variáveis estão comentadas lá. As principais:

| Variável | Para quê |
|---|---|
| `DATABASE_URL` | banco; sem ela usa SQLite local (aceita Postgres também) |
| `SECRET_KEY` | assina cookies; obrigatória em produção |
| `MESA_ENV` | `development` (padrão) ou `production` |
| `INVITE_CODE` / `ALLOW_OPEN_REGISTRATION` | quem pode criar conta |
| `USER_IMAGE_QUOTA_MB` | cota de imagens por conta (padrão 3) |
| `HOST` / `PORT` | endereço e porta (padrão `127.0.0.1:5000`) |
| `TWILIO_*`, `MESSAGES_PER_DAY` | envio direto de SMS/WhatsApp (opcional, pago) |
| `RESEND_API_KEY`, `ADMIN_EMAIL` | e-mail de pedido de liberação de imagens (opcional) |

## Administração

- A **primeira conta** de um banco vazio é administradora e vê o menu *Administração*.
- Para tornar outra conta administradora (com o ambiente virtual ativo e `FLASK_APP=run.py`): `flask make-admin email@exemplo.com`.
- Outros comandos: `flask list-users`, `flask approve-images email@exemplo.com`, `flask grant-messaging email@exemplo.com`.

Contas que não são administradoras começam **sem poder enviar imagens**; a liberação é pelo menu *Administração → Imagens* (ou `flask approve-images`). Os campos de imagem ficam desabilitados, com explicação, até lá. O e-mail de aviso ao administrador (Resend) só funciona se você configurar `RESEND_API_KEY` e `ADMIN_EMAIL`; sem isso, os pedidos aparecem apenas na tela de Administração.

## Mensagens: WhatsApp e SMS

1. No cadastro do jogador, informe o **telefone** (com DDD; o `+55` é completado sozinho) e marque o **consentimento** de que ele aceita receber mensagens.
2. Em **Mensagens**, escolha o tipo de dado, os destinatários e gere a prévia. Cada texto é editável.
3. Botões:
   - **WhatsApp** → abre `wa.me` com a mensagem pronta no *seu* WhatsApp (você só aperta enviar).
   - **SMS** → abre o app de SMS do aparelho com a mensagem pronta.
   - **Copiar texto**.
   - **Enviar pelo servidor** (opcional, ver abaixo).

As mensagens só usam **dados públicos**; notas privadas, segredos de NPC e observações do mestre nunca entram no texto (há teste automatizado para isso).

### Envio direto pelo servidor (opcional, Twilio)

Crie uma conta no [Twilio](https://www.twilio.com/) e configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM` e/ou `TWILIO_WHATSAPP_FROM` (veja `.env.example`). Isso consome crédito seu, então **cada conta precisa ser liberada manualmente**: `flask grant-messaging amigo@exemplo.com` (`--revoke` revoga). Há limite diário por conta (`MESSAGES_PER_DAY`) e um registro de envios (sem o texto). O `iniciar.bat` desliga esse recurso de propósito.

## Contas e segurança

- Recuperação de senha: **e-mail + palavra-chave** definida no cadastro (não há envio de e-mail). Sem a palavra-chave não há como recuperar — troque-a em *Minha conta*.
- Cada conta é isolada das demais.
- Backup (menu *Backup*): a restauração substitui **somente os seus dados**, em uma transação (se falhar, nada muda).

## Desenvolvimento e testes

```powershell
.\setup.ps1                      # venv + dependências de desenvolvimento + banco
.\.venv\Scripts\python.exe -m pytest
```

Os testes usam SQLite em memória e **nunca** tocam nos seus dados. Para rodar contra um Postgres de teste, defina `TEST_DATABASE_URL` (⚠ o banco indicado é **apagado e recriado**; use um banco descartável).

## Estrutura

```
run.py               entrada (`python run.py` ou `flask`)
local/               iniciar.bat / iniciar.ps1 (uso local), LEIA-ME.md, dados/ (seu banco; fora do git)
app/                 fábrica, models, services, forms, routes, templates, static
  services/auth.py        Argon2id, sessões, bloqueio, recuperação
  services/ownership.py   isolamento por usuário (get_or_404 verifica o dono)
  services/backup.py      backup/restauração por usuário
  services/messaging.py   textos, links WhatsApp/SMS, Twilio
  services/uploads.py     validação/recodificação de imagens (Pillow)
migrations/          Alembic (SQLite e Postgres)
tests/               pytest (incluindo varredura de IDOR)
```

Novo módulo: `models/x.py`, `forms/x.py`, `routes/x.py` (registrar em `routes/__init__.py`), migration (`flask db migrate -m "..."`, revisar, `flask db upgrade`). **Regra de ouro:** todo registro novo deve pertencer a um usuário (direto ou via campanha) e as rotas devem carregá-lo com `get_or_404` (que confere o dono); some um teste em `tests/test_isolation.py`.

## Solução de problemas

- **"python não é reconhecido"**: reinstale o Python marcando *Add python.exe to PATH*.
- **Demora na primeira execução**: normal (instala dependências e Pillow/psycopg).
- **Porta em uso**: defina outra com `$env:PORT = "5055"` antes de iniciar.
- **Erro de banco/tabelas**: rode `flask db upgrade` (o `iniciar.bat` já faz isso) e confira `http://127.0.0.1:5000/health`.
- **Esqueci a senha e a palavra-chave**: peça a um administrador ou, em último caso, apague `local\dados` para recomeçar (perde os dados — faça backup antes).

## Limitações conhecidas

- Sem recuperação por e-mail (por escolha).
- Não há limite por IP no login (o bloqueio é por conta).
- Imagens: cota pequena (3 MB/conta) por padrão, ajustável com `USER_IMAGE_QUOTA_MB`.
- O suporte a Postgres é opcional e coberto pela suíte em SQLite e pelo DDL gerado; use `TEST_DATABASE_URL` para validar no seu ambiente.
