# Condor AI Cloud

Aplicativo privado e instalavel para manter chat, fatos e anotacoes do Condor
disponiveis no celular e no PC. Ele e um sistema proprio do Condor: nao usa o
banco do ARTX Hub e nao publica nenhuma porta do computador.

Existe uma unica mente canonica, `condor-kaua-primary-v1`, usando a identidade
`condor-core-identity-v1`. PC e celular sao apenas interfaces dessa mesma mente;
o Supabase e persistencia temporaria e nunca representa um segundo assistente.

## O que continua funcionando com o PC desligado

- chat com IA;
- historico da conversa;
- criacao e consulta de anotacoes;
- memoria que ja foi sincronizada.

Com o PC desligado, funcoes que dependem fisicamente do Windows, de arquivos
locais, cameras, Arduino ou outros dispositivos aparecem como indisponiveis. O
cloud nunca finge que executou uma acao local.

## Arquitetura e seguranca

- Next.js na Vercel serve a PWA e as rotas privadas;
- Supabase Auth aceita somente o usuario criado pelo dono;
- RLS limita todas as linhas a `auth.uid()`;
- conversa, fatos, notas e eventos sao cifrados em AES-256-GCM antes de chegar
  ao banco;
- a chave de cifra e a chave OpenAI existem apenas nas variaveis protegidas da
  Vercel;
- o PC guarda access/refresh tokens somente no cofre cifrado do Condor;
- senha, tokens, comandos, arquivos, biometria e auditoria nao entram no sync.

## Criar a infraestrutura exclusiva

1. Crie um projeto Supabase novo, exclusivo para o Condor.
2. No SQL Editor desse projeto, execute `supabase/schema.sql`.
3. Em Authentication, mantenha cadastro publico desativado e crie manualmente
   somente o usuario do Kaua.
4. Crie um projeto Vercel apontando o diretorio `cloud`.
5. Configure as variaveis listadas em `.env.example` no painel da Vercel.
6. Gere `CONDOR_CLOUD_ENCRYPTION_KEY` com 32 bytes aleatorios em base64. Guarde
   uma copia segura: trocar ou perder essa chave torna o conteudo anterior
   ilegivel.
7. Publique e abra a URL HTTPS no celular. Entre com o usuario privado e use a
   opcao do navegador para instalar na tela inicial.
8. No Condor do PC, abra `CELL` e informe URL da Vercel, URL/chave publica do
   Supabase e o mesmo login privado.

Nunca coloque `.env.local`, `OPENAI_API_KEY`, senha, token ou a chave de cifra no
Git. A chave `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` e publica por definicao; a
protecao dos dados continua sendo Auth + RLS + cifra da aplicacao.

## Migracao futura para nucleo proprio

O contrato de sincronizacao usa IDs de origem e eventos idempotentes justamente
para permitir exportar a mente cifrada e trocar o Supabase por um servidor do
Kaua sem criar outra identidade. Quando houver um aparelho proprio ligado 24h,
a infraestrutura muda; `condor-kaua-primary-v1` e seu historico permanecem.

## Desenvolvimento local

```powershell
Copy-Item .env.example .env.local
npm.cmd install
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run dev
```

Use apenas valores de teste no arquivo local. O arquivo `.env.local` e ignorado
pelo Git.
