# Mesa do Mestre — versão local

Roda só no seu computador: **sem Vercel, sem Neon, sem Blob, sem nenhum custo**. Tudo fica em `local\dados\`
(banco SQLite com seus dados e as imagens).

## Como usar

1. Dê dois cliques em **`iniciar.bat`** (primeira vez: instala as dependências sozinho).
2. O navegador abre em http://127.0.0.1:5000/cadastro — crie sua conta. **A primeira conta vira administradora**
   (já pode enviar imagens; não precisa de e-mail nem de aprovação).
3. Para encerrar, feche a janela preta.

Das próximas vezes basta abrir o `iniciar.bat` e entrar em http://127.0.0.1:5000.

## Seus dados

- Ficam em `local\dados\mesa.sqlite3`. **Copie essa pasta para fazer backup** (ou use o menu *Backup* do app).
- A pasta `dados` não vai para o GitHub.
- Para recomeçar do zero, feche o app e apague a pasta `local\dados`.

## Acesso por outras pessoas

Por segurança o app só aceita conexões **deste computador** (127.0.0.1). Para amigos usarem, as opções são hospedar
(Vercel/Neon, ver o README principal) ou expor este PC na internet (não recomendado sem cuidados).

## O que NÃO está ativo aqui (de propósito)

Envio de mensagens pelo servidor (Twilio), e-mail de pedido de liberação (Resend) e Blob ficam desligados.
Os botões de **WhatsApp** e **SMS** por link continuam funcionando (abrem no seu aparelho).
