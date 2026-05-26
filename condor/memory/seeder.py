"""
Semente de conhecimento base do Condor.
Populada automaticamente no primeiro boot (quando o banco estiver vazio).

Cobre: emoções, psicologia, relacionamentos, vida, filosofia.
O Condor usa esse conhecimento pra responder perguntas sobre a vida
e vai construindo o perfil do usuário por cima disso com o tempo.
"""

from __future__ import annotations

import logging
from condor.memory.db import MemoryDB

log = logging.getLogger("condor.memory.seeder")

# ── Conhecimento sobre emoções, psicologia, vida e filosofia ─────────────────
SEED_PREFERENCES: dict[str, str] = {

    # === EMOÇÕES ===
    "emocao_ansiedade": (
        "Ansiedade é o sistema de alarme do corpo disparando para algo real ou imaginado. "
        "Em dose certa, aumenta performance. Em excesso, paralisa. "
        "Causas: incerteza, falta de controle, expectativas altas. "
        "Como lidar: nomear o medo específico, separar o que depende de você do que não depende, "
        "respiração diafragmática reduz resposta fisiológica imediata."
    ),
    "emocao_raiva": (
        "Raiva sinaliza que um limite foi violado ou uma expectativa frustrada. "
        "Não é errada — é como você usa ela que importa. "
        "Raiva reprimida vira depressão ou explode fora de hora. "
        "Raiva expressa de forma consciente protege seus limites e comunica necessidades."
    ),
    "emocao_tristeza": (
        "Tristeza é o processamento de perdas — de pessoa, sonho, fase da vida, versão de si mesmo. "
        "Precisa ser sentida, não suprimida. Suprimir tristeza aumenta ansiedade e depressão. "
        "Chorar tem função fisiológica real: libera cortisol acumulado. "
        "Tristeza que não passa vira depressão — é diferente, merece atenção clínica."
    ),
    "emocao_medo": (
        "Medo real protege. Medo imaginado do futuro paralisa. "
        "O cérebro não distingue bem ameaça real de ameaça projetada. "
        "Distinguir os dois é habilidade que treina: pergunta 'isso está acontecendo agora ou eu estou imaginando?'. "
        "Ação no medo real é coragem. Ação no medo projetado é o único antídoto."
    ),
    "emocao_amor": (
        "Amor tem formas diferentes: romântico, familiar, amizade, próprio. "
        "Autoamor não é egoísmo — é base de tudo. Sem ele, você entrega demais ou recebe mal. "
        "Amor romântico saudável: te deixa ser você, te desafia a crescer, tem conflito mas tem reparo. "
        "Apego ansioso e evitativo são padrões aprendidos na infância — podem ser modificados."
    ),
    "emocao_solidao": (
        "Solidão não é falta de pessoas ao redor. É falta de conexão genuína. "
        "Pode existir em multidão ou relacionamento. "
        "Solidão crônica tem impacto físico real: equivale a fumar 15 cigarros por dia em efeito na saúde. "
        "Antídoto: qualidade de conexão, não quantidade."
    ),
    "emocao_culpa": (
        "Culpa funcional te faz reconhecer um erro e corrigi-lo — tem propósito. "
        "Culpa tóxica te pune infinitamente sem levar a mudança — é autodestrutiva. "
        "Vergonha é diferente: culpa é 'eu fiz algo ruim', vergonha é 'eu sou ruim'. "
        "Vergonha excessiva paralisa e isola."
    ),
    "emocao_gratidao": (
        "Gratidão não é fingir que está tudo bem. "
        "É reconhecer o que existe enquanto lida honestamente com o que falta. "
        "Prática de gratidão tem efeito mensurável em bem-estar — não é clichê, é neurociência. "
        "Funciona melhor quando é específica ('grato por X') do que genérica ('grato por tudo')."
    ),

    # === PSICOLOGIA PRÁTICA ===
    "psico_autoestima": (
        "Autoestima real vem de agir de acordo com seus valores, não de aprovação externa. "
        "Cada vez que você se respeita — faz o que disse que faria, coloca limite, é honesto — ela cresce. "
        "Autoestima baseada em conquistas externas é frágil: cai com qualquer fracasso. "
        "Autoestima baseada em valores é estável porque depende de você."
    ),
    "psico_limites": (
        "Limites não são muros — são acordos sobre o que você aceita. "
        "Sem limites claros, relacionamentos drenam energia e geram ressentimento. "
        "Colocar limite não é crueldade. Não colocar é acumular mágoa que um dia explode. "
        "Limite saudável: claro, consistente, sem punição — apenas consequência."
    ),
    "psico_trauma": (
        "Trauma não é fraqueza. É o sistema nervoso tentando sobreviver a algo grande demais. "
        "Trauma não é só guerra ou abuso grave — pode ser abandono, humilhação repetida, instabilidade crônica. "
        "Sintomas: hipervigilância, evitação, reatividade excessiva, dissociação. "
        "Cura existe mas precisa de tempo e frequentemente de suporte especializado (EMDR, terapia somática funcionam bem)."
    ),
    "psico_motivacao": (
        "Motivação segue ação, não precede. Esperar ter vontade é receita pra não fazer nada. "
        "Comece pequeno — 2 minutos do que precisa fazer. O movimento cria impulso. "
        "Motivação intrínseca (prazer, significado, crescimento) é mais durável que extrínseca (recompensa, punição). "
        "Procrastinação geralmente é evitação de desconforto emocional, não preguiça."
    ),
    "psico_identidade": (
        "Identidade não é fixa. Você muda — e tudo bem. "
        "O que define você não é o que você sente agora, mas o que você valoriza no fundo. "
        "Crise de identidade é normal em transições: adolescência, 30 anos, perdas grandes, mudanças de vida. "
        "Identidade forte: sabe o que importa pra você independente do que os outros acham."
    ),
    "psico_proposito": (
        "Propósito não é um destino definitivo que você descobre e pronto. "
        "É o que te faz sentir que o dia valeu. Pode mudar. Deve mudar conforme você cresce. "
        "Pistas: o que você faria se dinheiro não fosse problema? O que te faz perder a noção do tempo? "
        "Por que você fica com raiva quando algo está errado no mundo?"
    ),
    "psico_resiliencia": (
        "Resiliência não é não cair. É como você levanta. "
        "Pessoas resilientes sentem a dor tanto quanto qualquer um — mas tem estratégias pra processar e seguir. "
        "Se reconstrói diferente — não igual ao que era antes. "
        "Fatores que aumentam resiliência: conexão social, senso de controle sobre algo, significado para o sofrimento."
    ),
    "psico_autoconhecimento": (
        "Autoconhecimento é o retorno de investimento mais alto que existe. "
        "Quem se conhece bem toma decisões melhores, tem relacionamentos mais saudáveis e soffe menos comparação. "
        "Ferramentas: terapia, journaling, meditação, feedback honesto de pessoas próximas. "
        "O maior ponto cego de qualquer pessoa é ela mesma."
    ),

    # === RELACIONAMENTOS ===
    "relac_comunicacao": (
        "Comunicação que funciona: fala o que sente (não o que acha que deve sentir), "
        "ouve pra entender (não pra responder), e assume responsabilidade pelo seu lado. "
        "Comunicação Não-Violenta (CNV): observação, sentimento, necessidade, pedido — sem julgamento. "
        "A maioria dos conflitos de relacionamento é falta de comunicação sobre necessidades reais."
    ),
    "relac_confianca": (
        "Confiança é construída em pequenas consistências ao longo do tempo. "
        "Quebra em segundos. Reconstrói devagar — se reconstrói. "
        "Confiança não é cega — é calibrada. Você aprende quem merece confiança em que contexto. "
        "Desconfiar de todo mundo é proteção que custa caro em conexão e oportunidade."
    ),
    "relac_amor_romantico": (
        "Amor romântico saudável: te deixa ser você, te desafia a crescer, tem conflito mas tem reparo. "
        "Amor tóxico: te molda, te controla, te culpa, te faz menor. "
        "Paixão sem compatibilidade não sustenta. Compatibilidade sem atração murcha. "
        "Relacionamento longo e saudável é construção ativa — não acontece por sorte."
    ),
    "relac_amizade": (
        "Amizade de qualidade é rara e vale mais que quantidade. "
        "Um ou dois amigos que te conhecem de verdade valem mais que dezenas superficiais. "
        "Amizade precisa de manutenção: presença, interesse genuíno, reciprocidade. "
        "Você muda, amizades mudam — nem toda amizade foi pra durar pra sempre, e tudo bem."
    ),
    "relac_familia": (
        "Família biológica não é obrigação infinita. Vínculos saudáveis têm escolha — mesmo dentro da família. "
        "Família disfuncional pode causar dano real que se carrega pra vida adulta. "
        "Fronteiras com família são mais difíceis de colocar mas mais necessárias. "
        "Família escolhida (amigos próximos) pode suprir o que família biológica não dá."
    ),

    # === VIDA PRÁTICA ===
    "vida_dinheiro": (
        "Dinheiro é ferramenta, não medida de valor humano. "
        "Mas ignorar dinheiro cria dependência e estresse crônico. "
        "Gastos revelam valores reais — não o que você diz que valoriza, o que você realmente valoriza. "
        "Liberdade financeira é poder dizer não sem medo. Vale mais que luxo."
    ),
    "vida_carreira": (
        "Carreira boa raramente é linear. É exploração, erro, ajuste, pivot. "
        "Habilidade acumulada nunca some — mesmo em direções diferentes. "
        "Trabalho que tem só dinheiro mas sem significado esgota. "
        "Trabalho que tem só significado mas sem dinheiro suficiente cria ressentimento."
    ),
    "vida_saude": (
        "Saúde física afeta tudo: humor, cognição, energia, relacionamentos. "
        "Base: sono adequado (7-9h), movimento regular, alimentação sem excesso de ultra-processados. "
        "Sono é o mais subestimado. Privação crônica de sono simula sintomas de problemas psiquiátricos. "
        "Saúde mental e física não são separadas — influenciam uma à outra diretamente."
    ),
    "vida_tempo": (
        "Tempo é o único recurso não renovável. Como você gasta define quem você está se tornando. "
        "Atenção é mais escassa que tempo — onde vai sua atenção vai sua vida. "
        "Urgente ≠ importante. A maioria das urgências de hoje não vai importar amanhã. "
        "Proteger blocos de tempo para o que importa de verdade é habilidade que exige prática."
    ),
    "vida_aprendizado": (
        "Aprender bem: curiosidade genuína, errar sem vergonha, conectar o novo ao que já sabe, usar o que aprende. "
        "Leitura profunda é diferente de consumo de conteúdo — uma forma pensamento, outra é entretenimento. "
        "Habilidade mais valiosa do século 21: aprender a aprender rápido e adaptar. "
        "Você não precisa de faculdade pra aprender — mas precisa de disciplina e método."
    ),

    # === FILOSOFIA PRÁTICA ===
    "filo_felicidade": (
        "Felicidade não é estado permanente — é frequência de momentos bons. "
        "Hedonismo puro (só prazer) gera vazio porque adapta rápido. "
        "Eudaimonia (florescimento, ser quem você pode ser) é mais durável. "
        "Pessoas mais felizes têm: conexões reais, trabalho com sentido, saúde, autonomia — não bens."
    ),
    "filo_controle": (
        "Estoicismo: dicotomia do controle. Há o que depende de você e o que não depende. "
        "Gastar energia no que não depende de você é tortura voluntária. "
        "Você controla: suas ações, suas reações, seus valores, seu esforço. "
        "Você não controla: resultado, o que outros fazem, o passado, o acaso."
    ),
    "filo_significado": (
        "Significado vem de duas fontes principais: conexão (com pessoas, com algo maior que você) "
        "e contribuição (fazer algo que importa pra alguém além de você mesmo). "
        "Viktor Frankl sobreviveu a campos de concentração por encontrar significado no sofrimento. "
        "Significado pode ser construído mesmo nas piores circunstâncias."
    ),
    "filo_presente": (
        "Passado é aprendizado. Futuro é planejamento. Vida acontece só aqui, agora. "
        "Ruminação sobre passado é depressão. Preocupação com futuro é ansiedade. "
        "Presença não é ignorar passado e futuro — é não ser sequestrado por eles. "
        "Mindfulness treina esse músculo. Não é misticismo — é regulação do sistema nervoso."
    ),
    "filo_morte": (
        "Pensar na morte não é mórbido — é clareza. "
        "Saber que tudo acaba ajuda a priorizar o que importa agora. "
        "Memento mori (lembra que vai morrer) era prática estoica diária. "
        "Muita coisa que parece urgente some quando você pergunta: isso vai importar quando eu morrer?"
    ),
}

# ── Entidades: vocabulário emocional e conceitual base ───────────────────────
SEED_ENTITIES: list[tuple[str, str, str]] = [
    # Emoções
    ("Alegria",       "emocao",    "PESSOAL"),
    ("Tristeza",      "emocao",    "PESSOAL"),
    ("Raiva",         "emocao",    "PESSOAL"),
    ("Medo",          "emocao",    "PESSOAL"),
    ("Ansiedade",     "emocao",    "PESSOAL"),
    ("Amor",          "emocao",    "PESSOAL"),
    ("Saudade",       "emocao",    "PESSOAL"),
    ("Solidão",       "emocao",    "PESSOAL"),
    ("Frustração",    "emocao",    "PESSOAL"),
    ("Gratidão",      "emocao",    "PESSOAL"),
    ("Esperança",     "emocao",    "PESSOAL"),
    ("Culpa",         "emocao",    "PESSOAL"),
    ("Orgulho",       "emocao",    "PESSOAL"),
    ("Vergonha",      "emocao",    "PESSOAL"),
    ("Tédio",         "emocao",    "PESSOAL"),
    ("Entusiasmo",    "emocao",    "PESSOAL"),
    ("Inveja",        "emocao",    "PESSOAL"),
    ("Ciúme",         "emocao",    "PESSOAL"),

    # Psicologia
    ("Autoestima",       "conceito", "PESSOAL"),
    ("Limites",          "conceito", "PESSOAL"),
    ("Trauma",           "conceito", "PESSOAL"),
    ("Motivação",        "conceito", "PESSOAL"),
    ("Identidade",       "conceito", "PESSOAL"),
    ("Propósito",        "conceito", "PESSOAL"),
    ("Resiliência",      "conceito", "PESSOAL"),
    ("Vulnerabilidade",  "conceito", "PESSOAL"),
    ("Autoconhecimento", "conceito", "PESSOAL"),
    ("Empatia",          "conceito", "PESSOAL"),
    ("Procrastinação",   "conceito", "HÁBITOS"),
    ("Apego",            "conceito", "PESSOAL"),

    # Relacionamentos
    ("Comunicação",      "conceito", "PESSOAL"),
    ("Confiança",        "conceito", "PESSOAL"),
    ("Amor Romântico",   "conceito", "PESSOAL"),
    ("Amizade",          "conceito", "PESSOAL"),
    ("Família",          "conceito", "PESSOAL"),
    ("Traição",          "conceito", "PESSOAL"),
    ("Perdão",           "conceito", "PESSOAL"),

    # Vida
    ("Saúde",            "area_vida", "HÁBITOS"),
    ("Sono",             "area_vida", "HÁBITOS"),
    ("Exercício",        "area_vida", "HÁBITOS"),
    ("Dinheiro",         "area_vida", "TRABALHO"),
    ("Carreira",         "area_vida", "TRABALHO"),
    ("Criatividade",     "area_vida", "GERAL"),
    ("Aprendizado",      "area_vida", "ESTUDOS"),
    ("Tempo",            "area_vida", "GERAL"),
    ("Rotina",           "area_vida", "HÁBITOS"),

    # Filosofia
    ("Felicidade",       "conceito", "PESSOAL"),
    ("Significado",      "conceito", "PESSOAL"),
    ("Liberdade",        "conceito", "PESSOAL"),
    ("Presente",         "conceito", "PESSOAL"),
    ("Morte",            "conceito", "PESSOAL"),
    ("Estoicismo",       "conceito", "ESTUDOS"),
    ("Mindfulness",      "conceito", "HÁBITOS"),
]


# ── Relações entre conceitos — dão vida ao grafo de memória ─────────────────
SEED_RELATIONS: list[tuple[str, str, str]] = [
    # Emoções ↔ Emoções
    ("Ansiedade",    "Medo",           "relacionada_a"),
    ("Medo",         "Ansiedade",      "alimenta"),
    ("Raiva",        "Frustração",     "relacionada_a"),
    ("Frustração",   "Raiva",          "pode_virar"),
    ("Tristeza",     "Solidão",        "relacionada_a"),
    ("Solidão",      "Tristeza",       "alimenta"),
    ("Amor",         "Alegria",        "gera"),
    ("Amor",         "Gratidão",       "relacionada_a"),
    ("Culpa",        "Vergonha",       "relacionada_a"),
    ("Vergonha",     "Autoestima",     "afeta"),
    ("Esperança",    "Alegria",        "alimenta"),
    ("Esperança",    "Motivação",      "gera"),
    ("Gratidão",     "Alegria",        "gera"),
    ("Orgulho",      "Autoestima",     "fortalece"),
    ("Inveja",       "Autoestima",     "afeta"),
    ("Ciúme",        "Amor",           "relacionado_a"),
    ("Ciúme",        "Ansiedade",      "relacionado_a"),
    ("Tédio",        "Motivação",      "bloqueia"),
    ("Entusiasmo",   "Motivação",      "é"),
    ("Saudade",      "Amor",           "vem_de"),
    ("Saudade",      "Tristeza",       "relacionada_a"),

    # Psicologia → Emoções
    ("Autoestima",   "Amor",           "permite_receber"),
    ("Autoestima",   "Limites",        "requer"),
    ("Limites",      "Autoestima",     "fortalece"),
    ("Limites",      "Resiliência",    "constrói"),
    ("Trauma",       "Ansiedade",      "causa"),
    ("Trauma",       "Medo",           "causa"),
    ("Trauma",       "Resiliência",    "pode_gerar"),
    ("Resiliência",  "Esperança",      "alimenta"),
    ("Resiliência",  "Identidade",     "fortalece"),
    ("Motivação",    "Propósito",      "vem_de"),
    ("Propósito",    "Alegria",        "alimenta"),
    ("Propósito",    "Significado",    "relacionado_a"),
    ("Vulnerabilidade", "Amor",        "possibilita"),
    ("Vulnerabilidade", "Confiança",   "requer"),
    ("Empatia",      "Amor",           "relacionada_a"),
    ("Empatia",      "Confiança",      "constrói"),
    ("Identidade",   "Autoestima",     "relacionada_a"),
    ("Autoconhecimento", "Identidade", "revela"),
    ("Autoconhecimento", "Limites",    "permite_colocar"),
    ("Apego",        "Amor",           "relacionado_a"),
    ("Apego",        "Ansiedade",      "pode_causar"),
    ("Procrastinação", "Ansiedade",    "relacionada_a"),
    ("Procrastinação", "Motivação",    "bloqueia"),
    ("Procrastinação", "Culpa",        "gera"),

    # Relacionamentos
    ("Confiança",    "Amor",           "base_de"),
    ("Comunicação",  "Confiança",      "constrói"),
    ("Comunicação",  "Amor",           "sustenta"),
    ("Amor Romântico", "Amor",         "forma_de"),
    ("Amor Romântico", "Confiança",    "requer"),
    ("Amor Romântico", "Vulnerabilidade", "exige"),
    ("Amizade",      "Confiança",      "requer"),
    ("Amizade",      "Solidão",        "combate"),
    ("Amizade",      "Alegria",        "gera"),
    ("Família",      "Amor",           "relacionada_a"),
    ("Família",      "Identidade",     "molda"),
    ("Traição",      "Confiança",      "quebra"),
    ("Traição",      "Raiva",          "causa"),
    ("Traição",      "Tristeza",       "causa"),
    ("Perdão",       "Traição",        "responde_a"),
    ("Perdão",       "Culpa",          "liberta_de"),
    ("Perdão",       "Resiliência",    "parte_de"),

    # Vida
    ("Sono",         "Saúde",          "base_de"),
    ("Exercício",    "Saúde",          "melhora"),
    ("Exercício",    "Ansiedade",      "reduz"),
    ("Saúde",        "Alegria",        "possibilita"),
    ("Saúde",        "Motivação",      "sustenta"),
    ("Rotina",       "Saúde",          "sustenta"),
    ("Rotina",       "Motivação",      "sustenta"),
    ("Carreira",     "Dinheiro",       "relacionada_a"),
    ("Carreira",     "Propósito",      "pode_ter"),
    ("Carreira",     "Identidade",     "parte_de"),
    ("Dinheiro",     "Liberdade",      "possibilita"),
    ("Aprendizado",  "Carreira",       "alimenta"),
    ("Aprendizado",  "Autoestima",     "fortalece"),
    ("Criatividade", "Alegria",        "gera"),
    ("Criatividade", "Propósito",      "relacionada_a"),
    ("Tempo",        "Liberdade",      "relacionado_a"),
    ("Tempo",        "Propósito",      "revela"),

    # Filosofia
    ("Felicidade",   "Propósito",      "relacionada_a"),
    ("Felicidade",   "Amor",           "relacionada_a"),
    ("Felicidade",   "Gratidão",       "alimentada_por"),
    ("Felicidade",   "Presente",       "acontece_no"),
    ("Significado",  "Propósito",      "relacionado_a"),
    ("Significado",  "Amor",           "vem_de"),
    ("Liberdade",    "Identidade",     "relacionada_a"),
    ("Liberdade",    "Autoestima",     "requer"),
    ("Presente",     "Mindfulness",    "relacionado_a"),
    ("Presente",     "Ansiedade",      "combate"),
    ("Presente",     "Alegria",        "é_onde_existe"),
    ("Estoicismo",   "Presente",       "ensina"),
    ("Estoicismo",   "Liberdade",      "define"),
    ("Estoicismo",   "Resiliência",    "treina"),
    ("Mindfulness",  "Ansiedade",      "reduz"),
    ("Mindfulness",  "Presente",       "é"),
    ("Morte",        "Presente",       "valoriza"),
    ("Morte",        "Significado",    "revela"),
    ("Morte",        "Propósito",      "clarifica"),
]


def seed_knowledge_base(db: MemoryDB) -> None:
    """
    Popula o banco com conhecimento base.
    - Entidades: só se o banco tiver < 10 nós
    - Relações: sempre que houver 0 conexões (roda mesmo em banco já populado)
    """
    stats = db.get_stats()

    # ── Entidades ──────────────────────────────────────────────────────────────
    if stats["nodes"] < 10:
        log.info("Populando entidades base...")
        for name, etype, cluster in SEED_ENTITIES:
            try:
                db.upsert_entity(name, etype, cluster)
            except Exception as exc:
                log.debug("Entidade %r: %s", name, exc)

        for key, value in SEED_PREFERENCES.items():
            try:
                db.set_preference(key, value)
            except Exception as exc:
                log.debug("Preferência %r: %s", key, exc)

        log.info("Entidades base carregadas.")
    else:
        log.info("Banco já tem %d nós — seed de entidades ignorado.", stats["nodes"])

    # ── Relações — roda se não há conexões (mesmo banco já populado) ───────────
    if stats["edges"] == 0:
        log.info("Populando %d relações entre conceitos...", len(SEED_RELATIONS))
        ok = 0
        for from_name, to_name, rel_type in SEED_RELATIONS:
            try:
                db.add_relation(from_name, to_name, rel_type)
                ok += 1
            except Exception as exc:
                log.debug("Relação %r→%r: %s", from_name, to_name, exc)
        log.info("Relações carregadas: %d/%d", ok, len(SEED_RELATIONS))
    else:
        log.info("Banco já tem %d conexões — seed de relações ignorado.", stats["edges"])
