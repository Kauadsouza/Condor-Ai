# Condor AI

[English](README.md) · **Português** · [Español](README.es.md)

Um sistema de IA pessoal que roda **no computador do dono**, com uma identidade persistente, memória criptografada e controle explícito sobre cada capacidade sensível.

Não é um invólucro em volta de um modelo. Modelos locais, OpenAI e Claude são motores intercambiáveis; o que permanece é a identidade, a política de memória, as permissões e a interface.

---

## Por que ele existe

Assistente de IA hospedado por terceiro tem um problema estrutural: a memória dele é de outra pessoa. Você conversa por meses, e aquele histórico — quem você é, o que já explicou, o que decidiu — vive num servidor que pode mudar de regra, de preço ou de dono.

O Condor inverte isso. A memória fica no disco do dono, criptografada; o modelo é uma peça trocável.

## Princípios de projeto

- **Uma mente só:** PC, visualizador móvel e o companheiro na nuvem são interfaces para a mesma identidade canônica.
- **Posse local:** o estado privado fica sob controle do dono e não é versionado junto com o código.
- **Automação que falha fechada:** ações no computador, em arquivos e em dispositivos físicos passam por política e aprovação explícita.
- **Independência de modelo:** o núcleo determinístico continua funcionando sem API paga.
- **Segurança inspecionável:** criptografia, verificação de integridade, encadeamento de auditoria e caminhos de recuperação são documentados e testados.

## Capacidades

- Núcleo FastAPI preso a `127.0.0.1`, com interface de desktop própria.
- Cofre e instantâneo de memória cifrados com **AES-256-GCM**, chave derivada por **scrypt**.
- Fatos, conversas, tarefas, estado de projeto e rascunhos versionados que persistem.
- Identidade estável `condor-core-identity-v1` acima do roteador de modelos.
- Conectores Local, OpenAI e Claude selecionáveis, com redação de segredos.
- Fala local, palavra de ativação opcional, visão computacional só para autenticação e geração de imagem privada.
- Ferramentas com permissão escopada para arquivos, aplicativos, pesquisa e desenvolvimento.
- Visualizador móvel **somente leitura** na rede privada — sem rota de comando, memória ou cofre.
- Integração com o ARTX Hub para organização, sem compartilhar permissões do PC nem memória privada.
- Condor X: espaço experimental para projeto 3D e simulações de engenharia delimitadas.
- Base opcional de PWA (`cloud/`) para conversa, notas e memória cifradas quando o PC está desligado.

## Backup: a única parte insubstituível

O código volta de um `git clone`. A **memória, a identidade e o cofre não** — eles existem só em `~/.condor`, nesta máquina.

Por isso o backup é automatizado, e não uma boa intenção:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
```

Isso pergunta a pasta de destino, pede a frase secreta **uma única vez** e agenda a execução diária, mais uma cinco minutos depois de cada login — para os dias em que o PC estava desligado no horário.

A frase fica protegida pelo Windows (DPAPI), legível só por esta conta nesta máquina. **O arquivo de backup continua portátil:** abre com a frase em qualquer computador — que é exatamente o ponto, se esta máquina morrer. São guardados os 14 mais recentes.

Testar a restauração faz parte do procedimento, porque um backup que ninguém restaurou é uma esperança, não um backup:

```powershell
powershell -File scripts\restore_condor_data.ps1 -BackupFile "<arquivo.enc>" -CondorHome "$env:TEMP\teste-restauracao"
```

## Fronteira de segurança

O núcleo completo tem de permanecer só em loopback. **Nunca exponha a porta `7777` à internet.** O visualizador móvel roda em processo e porta separados, restrito a redes privadas, exige pareamento e devolve apenas dados sanitizados de leitura.

Segredos, modelos biométricos, memória, configuração, registros e arquivos do usuário vivem fora do repositório, em `~/.condor`. O repositório restaura a aplicação, mas não restaura esse estado privado. Nunca publique nem recrie um `~/.condor` existente ao publicar o código.

Leia o [modelo de segurança](SECURITY.md), a [arquitetura](ARCHITECTURE.md) e o [guia de operação](OPERATIONS.md).

## Arquitetura em um olhar

```text
Interface de desktop / voz / projetos locais
                |
          Núcleo FastAPI local
                |
   identidade + política + memória cifrada
        /           |             \
 determinístico  modelo local   APIs opcionais

Fronteiras separadas:
- visualizador móvel somente leitura
- base do companheiro na nuvem, cifrada
- camada de organização do ARTX Hub
```

## Instalação no Windows

Requer Python 3.11 ou mais novo.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_new_windows_pc.ps1
```

Instalação manual:

```powershell
.\scripts\install.ps1
.\scripts\install_local_ai.ps1
.\scripts\run.ps1
```

Os downloads iniciais de modelo podem ser grandes. Depois disso, os modelos locais configurados rodam sem conta de IA externa.

## Verificação

```powershell
.\.venv\Scripts\python.exe testes\rodar_testes.py
.\.venv\Scripts\python.exe scripts\doctor.py
```

A suíte cobre política, criptografia do cofre, memória, identidade, roteamento de provedores, fronteiras de interface, segurança de dispositivos e as regras de simulação do Condor X — **sem exigir API paga**. É o repositório mais bem coberto do conjunto, com 114 testes.

O companheiro na nuvem é verificado à parte:

```powershell
Set-Location cloud
npm.cmd install
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

## Mapa do repositório

```text
condor/        Núcleo, memória, segurança, dispositivos, interface e motores de projeto
cloud/         Base opcional do companheiro PWA cifrado
deploy/        Exemplos de implantação em rede privada
scripts/       Instalação, diagnóstico, backup e execução local
testes/        Suíte de regressão de segurança e comportamento
windows/       Identidade do lançador nativo do Windows
```

## Situação, sem maquiagem

O Condor é um sistema pessoal de pesquisa e desenvolvimento em uso, não um assistente de consumo acabado. A operação local no PC e as fronteiras de segurança testadas estão implementadas. O companheiro na nuvem é uma base que ainda precisa de infraestrutura própria, autenticação real e validação de ponta a ponta. As ferramentas do Condor X são protótipos e simulações — não afirmam desempenho físico validado.

## Licença

Projeto de portfólio com código visível e proprietário. A visibilidade pública não concede permissão para copiar, redistribuir ou comercializar.

Feito e mantido por [Kauã Diniz Souza](https://github.com/Kauadsouza).
