# Segurança — Mesa do Mestre

Resumo do modelo de segurança do app hospedado (multiusuário) e do que é verificado por testes.

## Isolamento entre usuários (o ponto mais importante)

- Todo dado pertence a um usuário: `Campaign.owner_id` e `Player.owner_id` (e `FileAsset.owner_id`); tudo mais pertence a uma campanha. Chaves estrangeiras com `ON DELETE CASCADE`.
- **Todas** as rotas carregam registros por `get_or_404`, que devolve **404** (não 403, para não revelar que o id existe) se o dono não for o usuário logado (`services/ownership.py`). Listagens partem de `my_campaigns()`/`my_players()` ou fazem *join* com a campanha do usuário.
- Vínculos entre registros (personagem↔jogador, participantes de sessão, posses de itens…) são validados no servidor: tudo precisa ser da mesma campanha **e** da mesma conta. IDs de outra conta guardados na sessão/cookie são ignorados.
- Backup/restauração são **por usuário**: o arquivo contém só os dados dele; a restauração gera ids novos e remapeia todas as chaves, então nenhum arquivo consegue apontar para registros de terceiros nem sobrescrevê-los.
- `tests/test_isolation.py` percorre dezenas de rotas (GET/POST/JSON) com ids de outro usuário e confirma 404 e dados intactos.

## Autenticação

- Senhas e palavra-chave de recuperação: **Argon2id**; nunca em texto, nunca em log.
- Sessão: token aleatório de 32 bytes em cookie `HttpOnly`, `SameSite=Lax`, `Secure` em produção; no banco só o **hash SHA-256**. 14 dias; sair/trocar senha/recuperar senha encerram as sessões.
- Bloqueio de 10 min após 5 tentativas erradas (login e recuperação compartilham o contador). Mensagens idênticas para e-mail inexistente e senha errada; hash "fantasma" para igualar o tempo de resposta.
- Cadastro: código de convite (`INVITE_CODE`); fechado em produção se não houver código. Redirecionamento `next` só aceita caminhos locais. Sessão é limpa no login (anti fixação).
- Toda rota exige login, exceto login/cadastro/recuperação/estáticos/`/health`.

## Aplicação

- CSRF em todos os POST (inclusive os JSON, via cabeçalho). Auto-escape do Jinja; CSP sem scripts inline; `X-Frame-Options: DENY`; `nosniff`; HSTS em produção; `Cache-Control: no-store` nas páginas.
- Uploads: extensão, tamanho e conteúdo verificados e **recodificados com Pillow** (remove EXIF, limita a 800 px, nunca SVG), cota por conta, nome gerado, servido só ao dono por `/media/<id>`.
- Mensagens: só dados públicos (teste garante que segredos/notas do mestre não vazam); destinatário precisa de telefone **e consentimento**; envio pelo servidor exige conta liberada, limite diário e fica registrado (sem o texto).
- SQL somente via ORM/parâmetros; `LIKE` com escape; erros 500 sem rastreamento.

## Operação

- `SECRET_KEY` obrigatória em produção (o app não sobe sem ela). Segredos só em variáveis de ambiente.
- Restauração de backup valida o .zip (entradas permitidas, tamanho, JSON, colunas, imagens) antes de tocar no banco e executa numa transação.

## Fora do escopo / riscos aceitos

- Sem limitação por IP no login (bloqueio é por conta).
- Recuperação por palavra-chave: quem a souber redefine a senha; trate-a como uma segunda senha.
- O telefone dos jogadores é dado pessoal: mantenha o consentimento marcado só quando existir e exclua a conta para apagar tudo.
