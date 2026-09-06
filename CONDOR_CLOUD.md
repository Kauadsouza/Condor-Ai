# CELL: Condor no PC e no celular

A aba `CELL` da interface local e a ponte de configuracao e acompanhamento do
Condor Cloud. O aplicativo hospedado vive em `cloud/` e permanece independente
do ARTX Hub.

Invariante: existe somente a mente `condor-kaua-primary-v1`, com a identidade
`condor-core-identity-v1`. "Local", "cloud", "PC" e "celular" indicam apenas o
ponto de acesso ou a infraestrutura; nunca personalidades ou memorias separadas.

Fluxo de dados:

```text
Condor local cifrado -> HTTPS de saida -> API Condor Cloud -> Supabase com RLS
       ^                                                        |
       +---------------- eventos cifrados de sync --------------+

Celular/PWA -> login privado -> API Condor Cloud -> mesma memoria online
```

O servidor local continua limitado a `127.0.0.1:7777`. A visualizacao antiga da
porta `7778` continua privada, somente leitura e separada deste recurso. Nada no
CELL transforma o computador em servidor publico.

Credenciais de sessao do Cloud ficam exclusivamente no cofre existente do
Condor. Desconectar pela aba apaga esses tokens, sem apagar a memoria local ou o
conteudo hospedado.

Veja `cloud/README.md` para provisionamento, variaveis e publicacao.
