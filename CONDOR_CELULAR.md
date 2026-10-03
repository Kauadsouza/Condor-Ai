# CONDOR no iPhone

A mesma mente do PC no celular, por chat e por voz. Com fone conectado
(AirPods ou com fio), a voz sai no fone.

## Como liga (uma vez)

1. No PC, aba **CELL**: **ENTRAR** abre o login do Tailscale no navegador. Entre
   com a sua conta (Google, Apple ou Microsoft).
2. No iPhone, instale **Tailscale** da App Store e entre com a **mesma conta**.
3. De volta na aba CELL, **LIGAR**. Na primeira vez o Tailscale pode abrir uma
   página pedindo para liberar HTTPS na conta: libere e clique LIGAR de novo.
4. **GERAR QR CODE** e aponte a câmera do iPhone. Digite a palavra de acesso.
5. No Safari, **Compartilhar → Adicionar à Tela de Início**: vira um app "Condor".

## Como usa

- **Mensagem:** escreve e envia; responde em texto formatado (listas, negrito, código).
- **Foto:** botão ＋ tira ou escolhe uma foto; a visão local analisa no PC.
- **Microfone:** toca, fala, ele percebe quando você parou e responde em voz.
- **Escuta:** com a tela aberta, diga **"Condor, na escuta"** (vale no PC também).
  Ele responde "Tô na escuta, pode falar." e a conversa fica aberta: é só falar,
  sem repetir o nome, até 2 minutos de silêncio. "Condor" sozinho ou "Condor,
  abre X" sem "na escuta" é ignorado. O iPhone não deixa site ouvir com a tela
  bloqueada, então a tela fica acesa enquanto a escuta está ligada.
- **Menu ☰:** Nova conversa (a anterior fica guardada), Conversas anteriores,
  Galeria (toque para ver grande; toque duplo aproxima) e Memória (procurar e
  esquecer o que ele sabe de você).
- **Segure uma mensagem:** copiar, apagar (some do PC e do celular e ele esquece
  aquela troca) e 👍/👎 nas respostas.
- Funciona em casa e na rua (4G), desde que o PC esteja ligado, acordado e com
  internet. Se o PC acabou de ligar e o CONDOR está trancado, destranque pelo
  próprio celular com a palavra de acesso.
- Ações perigosas pedem a palavra de acesso digitada, igual ao PC.

## Segurança

```text
iPhone ──(rede privada Tailscale, HTTPS)──► tailscale serve ──► 127.0.0.1:7778 (canal do celular)
                                                                     │
                                                    mesma sessão, memória e ferramentas do PC
```

- Nada fica aberto na internet nem no Wi-Fi: o canal escuta só no `127.0.0.1` e o
  `tailscale serve` o publica apenas para os aparelhos da sua conta Tailscale.
- Parear exige o convite do QR (uso único, 5 minutos, 5 tentativas) **e** a
  palavra de acesso. O celular recebe um token de 180 dias em cookie
  `HttpOnly; Secure; SameSite=Strict`; o PC guarda só o hash
  (`~/.condor/security/celulares.json`).
- A aba CELL lista os aparelhos pareados e revoga na hora.
- A fala só sai do celular quando há voz; a transcrição é feita no PC
  (Whisper local). Na escuta contínua, o Vosk barra o que não soa como "Condor"
  antes do Whisper confirmar o nome.
