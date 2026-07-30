# Ligando o Condor — passo a passo

Três coisas e ele está de pé. A primeira é obrigatória, a segunda é o que faz
ele te ouvir, a terceira é dois cliques.

---

## 1. A chave da OpenAI — o cérebro

Sem isso ele não pensa. Nada mais funciona de verdade.

1. Entre em **https://platform.openai.com/signup** e crie a conta (ou faça
   login com a mesma conta do ChatGPT — serve).

2. **Ponha crédito.** Isto é o que a maioria esquece: assinar o ChatGPT Plus
   **não** dá crédito de API, são coisas separadas e cobradas à parte.

   Vá em **Settings → Billing → Add payment details** e adicione uns **US$ 5**.
   Dá pra semanas de uso normal.

3. Vá em **https://platform.openai.com/api-keys** → **Create new secret key**.
   Copie na hora: a OpenAI só mostra uma vez.

4. Abra o arquivo `.env` na pasta do Condor e cole:

   ```
   OPENAI_API_KEY=sk-proj-cole-a-sua-aqui
   ```

Se errar algo aqui, a tela **ERROS** do Condor te diz exatamente o quê.

---

## 2. A palavra "Condor" — a escuta

Sem isso ele funciona só digitando na janela. Com isso, ele te ouve.

### 2.1 A chave (grátis, 2 minutos)

1. Entre em **https://console.picovoice.ai/signup**.
2. Na primeira tela já aparece o **AccessKey**. Copie.
3. Cole no `.env`:

   ```
   PICOVOICE_ACCESS_KEY=cole-a-sua-aqui
   ```

Só com isso ele já acorda — mas responde ao nome **"Jarvis"**, que é uma das
palavras que já vêm prontas. Pra ele atender por "Condor", faça o passo 2.2.

### 2.2 Treinar a palavra "Condor" (mais 2 minutos)

1. No mesmo site, vá em **Porcupine** no menu da esquerda.
2. Em **Wake Word**, digite `Condor`.
3. Em **Language**, escolha **Portuguese**.
4. Clique em **Train** e escolha a plataforma **Windows (x86_64)**.
5. Baixe o `.zip`. Dentro tem dois arquivos que importam:
   - `Condor_pt_windows_v3_0_0.ppn` — a palavra
   - `porcupine_params_pt.pv` — o modelo do português

6. Crie a pasta `data\wake\` dentro do Condor e jogue os **dois** arquivos lá:

   ```
   data\wake\Condor_pt_windows_v3_0_0.ppn
   data\wake\porcupine_params_pt.pv
   ```

Pronto. Ele acha os arquivos sozinho no próximo boot e passa a atender por
"Condor". Se o `.pv` do português faltar, ele não sobe — os dois têm que estar lá.

---

## 3. Ligar

Instale as dependências uma vez:

```bash
pip install -r requirements.txt
```

E então **dois cliques em `condor_launcher.pyw`**.

Não vai aparecer nada. É esse o ponto: ele está rodando escondido, escutando.

Fale **"Condor, tudo bem?"** e a janela abre.

### Pra ele subir junto com o Windows

Botão direito em `instalar_inicializacao.ps1` → **Executar com PowerShell**.

Pra desfazer: `remover_inicializacao.ps1`.

---

## Comandos do dia a dia

**Ver o que ele está fazendo agora:**

```bash
Get-Content data\condor.log -Wait -Tail 30
```

**Ver tudo que ele já rodou no seu PC:**

```bash
Get-Content data\auditoria.log -Tail 40
```

**Parar o Condor:**

```bash
Get-Process pythonw | Stop-Process
```

**Abrir a janela sem falar** (útil pra testar): abra
`http://127.0.0.1:7777` no navegador, ou clique no orbe da tela.

---

## Testando se está tudo certo

Fale, um de cada vez:

| Você fala | O que tem que acontecer |
|---|---|
| "Condor, que horas são?" | responde falando, sem abrir nada |
| "Condor, como está meu PC?" | fala CPU, RAM, disco, bateria |
| "Condor, cria um arquivo teste.txt na área de trabalho" | o arquivo aparece lá |
| "Condor, o que tem na minha tela?" | tira print e descreve o que está vendo |
| "Condor, meu time é o Flamengo" | não faz nada de especial... |
| *(espere 2 min, chame de novo)* "Condor, qual meu time?" | **lembra** — isso é a memória funcionando |

Pra testar a trava de senha, peça algo pesado tipo *"Condor, reinicia o PC"*.
Ele vai parar e pedir a senha (`teste`). Responda **errado** de propósito na
primeira vez pra ver que ele barra mesmo.

---

## Ajustes

Tudo em `data\config.yaml` (criado sozinho no primeiro boot):

| o que | onde | padrão |
|---|---|---|
| tempo até dormir | `sessao.timeout_segundos` | 120 |
| voz dele | `voz.voz` | `onyx` (tem `alloy`, `echo`, `fable`, `nova`, `shimmer`) |
| velocidade da fala | `voz.velocidade` | 1.0 |
| quanto silêncio encerra sua fala | `voz.silencio_para_parar` | 1.3s |
| sensibilidade da escuta | `escuta.sensibilidade` | 0.6 (mais alto = dispara mais fácil) |
| modelo | `cerebro.modelo` | `gpt-4o` |
| o que pede senha | `seguranca.exigir_senha` | as quatro categorias |

Senha e nomes ficam no `.env`.

---

## Quando algo não funciona

**"Ele não me ouve"**
Abra a tela **ERROS** na janela. Se disser *escuta desligada*, falta a chave
do Picovoice. Se a chave estiver lá, confira em `data\condor.log` qual
microfone ele pegou — se for o errado, mude `escuta.indice_microfone` no
config (0, 1, 2...).

**"Ele acorda sozinho do nada"**
A sensibilidade está alta. Baixe `escuta.sensibilidade` pra 0.45.

**"Ele responde mas não faz nada no PC"**
Olhe `data\auditoria.log`. Se a ação foi barrada, era catastrófica e a senha
não foi confirmada.

**"Não abre nada quando eu chamo"**
Veja se o processo está vivo: `Get-Process pythonw`. Se não estiver, rode o
launcher pelo terminal pra ver o erro na cara:

```bash
python -m condor -v
```
