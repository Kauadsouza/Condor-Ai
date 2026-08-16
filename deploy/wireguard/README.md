# WireGuard para um futuro segundo equipamento proprio

Este modelo nao e ativado na fase PC-only. Ele existe para evitar que, no
futuro, o Condor seja exposto diretamente na internet.

Regras:

1. use somente equipamentos administrados por voce;
2. gere as chaves em cada equipamento; nunca grave chaves reais no repositorio;
3. mantenha o firewall fechado por padrao;
4. nao mude o servidor Condor de `127.0.0.1` sem adicionar um proxy local com
   autenticacao mutua dentro do tunel;
5. autorize cada identidade Ed25519 do Condor separadamente;
6. remova imediatamente peers perdidos ou substituidos.

O arquivo `condor-pc.conf.example` e apenas um esqueleto. WireGuard protege o
transporte; nao substitui o cofre, a identidade, as aprovacoes ou a auditoria.
