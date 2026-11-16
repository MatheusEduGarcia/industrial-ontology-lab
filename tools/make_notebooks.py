"""Builds the study notebooks (unexecuted). After this: execute them, then apply tools/didatico.py.

  python tools/make_notebooks.py
  cd notebooks && for f in 0*.ipynb; do jupyter nbconvert --to notebook --execute --inplace $f; done
  cd .. && python tools/didatico.py tools/didatico_conteudo.py .
"""
import nbformat as nbf
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "notebooks"
SETUP = """# Configuração: deixa a raiz do repositório no caminho de import
import sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd().parent))
import pandas as pd
pd.set_option("display.max_colwidth", 80)
from lab.graph import load_ontology, load_plant, query, MFG, PRD, MNT, QA, NRG, INV, ID"""


def nb(name, cells):
    book = nbf.v4.new_notebook()
    book.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    book.cells = [nbf.v4.new_markdown_cell(t) if k == "md" else nbf.v4.new_code_cell(t) for k, t in cells]
    nbf.write(book, ROOT / name)


M, C = "md", "code"

nb("01_ontologia_central.ipynb", [
(M, """# 01 · A ontologia central de manufatura

**Objetivo:** entender as três peças da camada semântica e construir a primeira delas, a **ontologia central**.

| Peça | O que é | Neste repositório |
|---|---|---|
| **Ontologia** | o vocabulário: classes, relações e regras | `ontology/*.ttl` |
| **Grafo de conhecimento** | os fatos da planta descritos com esse vocabulário | `data/plant.ttl` |
| **Contratos de dados** | o que um registro precisa ter para entrar no grafo | `shapes/shapes.ttl` (notebook 03) |

A ontologia central é pequena de propósito: só o que **todos** os domínios precisam. Hierarquia ISA-95, pontos de dado e eventos. Produção, manutenção, qualidade, energia e estoque vêm depois, como **extensões** (notebook 02)."""),
(C, SETUP),
(M, """## 1. Carregando a ontologia central

O arquivo está em **Turtle**, o formato texto do RDF. Cada linha é uma tripla `sujeito predicado objeto`."""),
(C, """core = load_ontology(domains=[])
print(f"{len(core)} triplas na ontologia central\\n")
texto = open("../ontology/core.ttl", encoding="utf-8").read()
print(texto[texto.index("mfg:Asset a owl:Class"):][:1500])"""),
(M, """## 2. As classes e a hierarquia de classes"""),
(C, """classes = query(core, '''
SELECT ?classe ?mae ?descricao WHERE {
  ?c a <http://www.w3.org/2002/07/owl#Class> ; rdfs:label ?classe .
  OPTIONAL { ?c rdfs:subClassOf/rdfs:label ?mae }
  OPTIONAL { ?c rdfs:comment ?descricao }
} ORDER BY ?mae ?classe''')
pd.DataFrame(classes)"""),
(M, """**Leitura:** `Enterprise`, `Site`, `Area`, `Line` e `Equipment` são todos subclasses de `Asset`. Isso permite perguntar "todos os ativos" sem listar os cinco tipos, e garante que qualquer coisa da hierarquia tenha um `assetId`.

`StateChange` é subclasse de `Event`: toda extensão que criar um evento novo (parada, ordem de produção, inspeção) herda `occurredOn`, `startTime` e `endTime`.

## 3. As relações (propriedades)"""),
(C, """props = query(core, '''
SELECT ?propriedade ?tipo ?de ?para WHERE {
  ?p rdfs:label ?propriedade ; a ?t .
  FILTER(?t IN (<http://www.w3.org/2002/07/owl#ObjectProperty>, <http://www.w3.org/2002/07/owl#DatatypeProperty>))
  BIND(STRAFTER(STR(?t), "#") AS ?tipo)
  OPTIONAL { ?p rdfs:domain/rdfs:label ?de }
  OPTIONAL { ?p rdfs:range ?r . BIND(REPLACE(STR(?r), "^.*[#/]", "") AS ?para) }
} ORDER BY ?tipo ?propriedade''')
pd.DataFrame(props)"""),
(M, """* **ObjectProperty** liga duas coisas (`partOf` liga um ativo a outro ativo).
* **DatatypeProperty** liga uma coisa a um valor (`unsTopic` liga um ponto de dado a uma string).
* `partOf` é **transitiva**: se a enchedora é parte da linha 1 e a linha 1 é parte da área de envase, a enchedora também é parte da área. Isso evita gravar todas as relações indiretas.

## 4. A ontologia aplicada: a planta de exemplo

Agora carregamos os **fatos** (`data/plant.ttl`) sobre o vocabulário. Uma empresa fictícia com duas plantas, três linhas e três máquinas por linha."""),
(C, """g = load_plant()
print(f"{len(g)} triplas (ontologia + dados)")
ativos = query(g, '''
SELECT ?tipo (COUNT(?a) AS ?quantidade) WHERE {
  ?a a ?c . ?c rdfs:subClassOf* mfg:Asset ; rdfs:label ?tipo .
  FILTER(STRSTARTS(STR(?a), STR(id:)))
} GROUP BY ?tipo ORDER BY DESC(?quantidade)''')
pd.DataFrame(ativos)"""),
(M, """Repare em `rdfs:subClassOf*`: o asterisco percorre a hierarquia de classes, então `Component` (definido na extensão de manutenção) entra na conta como ativo sem que a consulta precise saber que ele existe.

## 5. A hierarquia ISA-95 como grafo"""),
(C, """# A figura é gerada em DOT (Graphviz) a partir das triplas mfg:partOf. Veja lab/figures.py
from IPython.display import Image
from lab import figures
print(figures.hierarchy_dot(g)[:400], "...")
Image(filename=figures.render(figures.hierarchy_dot(g), "hierarchy"))"""),
(M, """**Leitura:** cada caixa é um ativo, a cor indica o nível ISA-95, e cada traço é uma tripla `filho mfg:partOf pai`. Os três componentes vermelhos ficam abaixo da enchedora da linha 1: é ali que a manutenção registra trocas de peça."""),
(M, """## 6. Transitividade na prática

Pergunta: **"tudo o que existe na planta de São Paulo"**. Ninguém gravou "enchedora partOf São Paulo"; o caminho `partOf+` (um ou mais saltos) encontra."""),
(C, """from lab import queries as q
pd.DataFrame(query(g, q.ASSETS_IN_SITE)).assign(asset=lambda d: d.asset.str.split("/id/").str[1], type=lambda d: d.type.str.split("#").str[1])"""),
(M, """São 12 ativos: a área, duas linhas, seis máquinas e três **componentes** da enchedora da linha 1, que vivem dois níveis abaixo da linha.

## Resumo

* A ontologia central define **identidade** (`assetId`), **contenção** (`partOf`, transitiva), **pontos de dado** (com o tópico do UNS) e **eventos**.
* Classes formam hierarquias (`subClassOf`), e consultas com `*` e `+` aproveitam isso sem conhecer cada tipo.
* Tudo que vier depois (produção, manutenção, qualidade...) **pendura** nesse núcleo, em vez de criar seu próprio modelo de máquina."""),
])

nb("02_extensoes_de_dominio.ipynb", [
(M, """# 02 · Extensões de domínio

**Objetivo:** ver como cada área da fábrica acrescenta seu vocabulário **sem redefinir o núcleo**. Produção, manutenção, qualidade, energia e estoque são arquivos separados que importam `core.ttl` e apenas adicionam classes e relações.

Por que separar? Porque cada domínio tem um dono diferente (PCP, manutenção, qualidade, utilidades, almoxarifado) e evolui em ritmo diferente. O núcleo é o acordo mínimo entre eles."""),
(C, SETUP + """
from lab.graph import DOMAINS
from rdflib import OWL, RDFS, RDF"""),
(M, """## 1. O que cada extensão traz"""),
(C, """linhas = []
nucleo = load_ontology(domains=[])
for d in DOMAINS:
    g = load_ontology(domains=[d])
    novas = set(g.subjects(RDF.type, OWL.Class)) - set(nucleo.subjects(RDF.type, OWL.Class))
    rels = [p for p in g.subjects(RDF.type, OWL.ObjectProperty) if (p, None, None) not in nucleo]
    herda = sorted({str(g.value(c, RDFS.subClassOf)).split("#")[-1] for c in novas if g.value(c, RDFS.subClassOf)})
    linhas.append({"domínio": d, "classes novas": ", ".join(sorted(str(c).split("#")[-1] for c in novas)),
                   "relações novas": len(rels), "estende do núcleo": ", ".join(herda)})
pd.DataFrame(linhas)"""),
(M, """**Leitura**

* `ProductionRun`, `Downtime`, `MaintenanceOrder`, `Inspection` e `Consumption` estendem `Event` do núcleo: todos herdam **quando** e **onde** (`startTime`, `endTime`, `occurredOn`). É isso que permite cruzar paradas com corridas de produção pelo tempo.
* `Component` estende `Asset`: um rolamento entra na hierarquia ISA-95 abaixo da máquina.
* `EnergyMeter` estende `DataPoint`: um medidor tem tópico no UNS como qualquer tag.

## 2. O esquema completo como grafo

Cada caixa é uma classe, cada seta cheia é uma relação (`domain → range`) e cada seta tracejada é `subClassOf`. As molduras agrupam por domínio."""),
(C, """from IPython.display import Image
from lab import figures
Image(filename=figures.render(figures.schema_dot(load_ontology()), "schema"))"""),
(M, """Todas as extensões convergem para os nós cinza do núcleo (`Equipment`, `Event`, `Asset`, `DataPoint`). É essa convergência que faz o grafo ser **um** e não cinco bancos de dados lado a lado.

## 3. Como os domínios aparecem nos dados"""),
(C, """g = load_plant()
contagem = query(g, '''
SELECT ?classe (COUNT(?x) AS ?instancias) WHERE {
  ?x a ?c . FILTER(STRSTARTS(STR(?x), STR(id:)))
  BIND(REPLACE(STR(?c), "^.*/(.*)$", "$1") AS ?classe)
} GROUP BY ?classe ORDER BY ?classe''')
pd.DataFrame(contagem)"""),
(M, """## 4. Um registro de cada domínio, lado a lado

Uma corrida de produção, a parada que aconteceu durante ela, e a inspeção do lote que ela gerou. Três sistemas diferentes no mundo real (MES, CMMS, QMS), três nós ligados aqui."""),
(C, """for iri in ["run/R-1042", "downtime/D-001", "inspection/Q-1042"]:
    print(f"--- {iri}")
    for p, o in sorted(g.predicate_objects(ID[iri])):
        print(f"   {g.namespace_manager.normalizeUri(p):<18} {str(o).split('/id/')[-1]}")"""),
(M, """**Leitura:** a corrida `R-1042` e a parada `D-001` apontam para a **mesma** enchedora (`occurredOn`), e os horários se sobrepõem. A inspeção aponta para o lote que a corrida produziu. Nenhuma tabela de junção foi criada para isso: as ligações vêm do vocabulário compartilhado.

## Resumo

* Extensões **importam** o núcleo e só **acrescentam**. Cada domínio pode ter seu dono e seu ciclo de revisão.
* Eventos de todos os domínios herdam tempo e ativo do núcleo: é por aí que se cruzam.
* O próximo passo é garantir que os dados que entram respeitem esse modelo (notebook 03)."""),
])

nb("03_contratos_de_dados_shacl.ipynb", [
(M, """# 03 · Contratos de dados com SHACL

**Objetivo:** separar duas coisas que costumam ser confundidas:

* a **ontologia** diz o que as coisas **significam** (uma parada é um evento que acontece numa máquina);
* o **SHACL** diz o que um registro **precisa conter** para ser aceito (toda parada não planejada precisa de um motivo).

Sem contrato, o grafo vira um depósito de dados incompletos, e a primeira consulta de Pareto mostra 40 % de paradas "sem motivo"."""),
(C, SETUP + """
from rdflib import Graph
from lab.graph import ROOT
from lab.validate import validate"""),
(M, """## 1. As regras

Um trecho do arquivo de shapes. Cada `sh:property` é uma regra sobre um caminho, e cada `sh:sparql` é uma regra que precisa olhar mais de um campo."""),
(C, """texto = open(ROOT / "shapes" / "shapes.ttl", encoding="utf-8").read()
print(texto[texto.index("shp:EquipmentShape"):][:1900])"""),
(M, """## 2. Validando a planta de exemplo"""),
(C, """planta = Graph().parse(ROOT / "data" / "plant.ttl")
ok, violacoes = validate(planta)
print("a planta respeita todos os contratos:", ok, "| violações:", len(violacoes))"""),
(M, """## 3. Validando o que uma integração descuidada mandaria

`data/broken.ttl` traz cinco registros plausíveis e errados: uma máquina nova sem identidade, um tópico copiado do símbolo do CLP, uma parada com horários trocados e sem motivo, uma ordem sem produto e uma inspeção com resultado em texto livre."""),
(C, """print(open(ROOT / "data" / "broken.ttl", encoding="utf-8").read())"""),
(C, """sujo = Graph().parse(ROOT / "data" / "plant.ttl")
sujo.parse(ROOT / "data" / "broken.ttl")
ok, violacoes = validate(sujo)
print("conforma:", ok, "| violações:", len(violacoes))
pd.DataFrame(violacoes)"""),
(M, """**Leitura, violação por violação**

* `new-palletizer` sem `assetId` e sem `partOf`: a máquina não tem identidade compartilhada com UNS, MES e CMMS, e não está em nenhuma linha. Ela nunca apareceria num OEE por linha.
* `new-palletizer/speed` com tópico `PLC1.DB10.Speed`: isso é o endereço do CLP, não um tópico do namespace. O contrato exige o caminho ISA-95 em minúsculas.
* `D-999`: fim antes do início **e** parada não planejada sem motivo. São duas regras que olham mais de um campo, por isso são `sh:sparql`.
* `WO-9999`: ordem sem produto e com quantidade zero.
* `Q-9999`: resultado "ok, looks fine" em vez de PASS, HOLD ou REJECT. Texto livre quebra qualquer indicador de qualidade.

## 4. Onde isso entra numa arquitetura real

O contrato roda **na entrada** do grafo: no conector do MES, no fluxo do Node-RED, no job de DataOps. Registro que falha vai para uma fila de correção com a mensagem da regra, em vez de entrar silenciosamente."""),
(C, """def aceitar(registro_ttl: str, grafo: Graph):
    candidato = Graph(); [candidato.add(t) for t in grafo]
    candidato.parse(data=registro_ttl, format="turtle")
    ok, v = validate(candidato)
    if ok:
        grafo.parse(data=registro_ttl, format="turtle"); return "aceito", []
    novos = [x for x in v if x["focus"] in registro_ttl]
    return "rejeitado", [x["message"] for x in novos]

base = Graph().parse(ROOT / "data" / "plant.ttl")
bom = '''@prefix mnt: <https://w3id.org/industrial-ontology-lab/maintenance#> . @prefix mfg: <https://w3id.org/industrial-ontology-lab/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<https://w3id.org/industrial-ontology-lab/id/downtime/D-100> a mnt:Downtime ; mnt:planned false ;
  mnt:causedBy <https://w3id.org/industrial-ontology-lab/id/failure-mode/jam> ;
  mfg:occurredOn <https://w3id.org/industrial-ontology-lab/id/acme/sao-paulo/packaging/line-2/filler-01> ;
  mfg:startTime "2026-11-10T14:00:00+00:00"^^xsd:dateTime ; mfg:endTime "2026-11-10T14:05:00+00:00"^^xsd:dateTime .'''
ruim = bom.replace("D-100", "D-101").replace("  mnt:causedBy <https://w3id.org/industrial-ontology-lab/id/failure-mode/jam> ;\\n", "")
print("D-100:", aceitar(bom, base))
print("D-101:", aceitar(ruim, base))"""),
(M, """## Resumo

* **Ontologia = significado**, **SHACL = contrato**. As duas são necessárias.
* Regras simples (`minCount`, `pattern`, `in`, `class`) cobrem a maioria dos casos; regras que comparam campos usam `sh:sparql`.
* Validar na entrada mantém o grafo confiável. Um grafo com dado ruim é pior que nenhum, porque as consultas parecem certas."""),
])

nb("04_consultas_de_negocio.ipynb", [
(M, """# 04 · Perguntas de negócio que atravessam domínios

**Objetivo:** mostrar por que vale a pena ter um grafo. Cada pergunta abaixo cruza pelo menos dois domínios e exigiria juntar MES, CMMS, QMS, almoxarifado e medição de energia, se cada um tivesse seu próprio modelo de máquina.

A planta de exemplo carrega uma pequena história, e o notebook termina com ela."""),
(C, SETUP + """
from lab import queries as q
import matplotlib.pyplot as plt
g = load_plant()
curto = lambda df: df.apply(lambda c: c.map(lambda v: v.split("/id/")[-1].split("#")[-1] if isinstance(v, str) else v))"""),
(M, """## 0. O turno inteiro numa figura

Antes das consultas, a linha do tempo de cada linha: corridas coloridas pelo resultado da inspeção do lote, e paradas por cima."""),
(C, """from lab import figures
figures.timeline(g); plt.show()"""),
(M, """Já dá para ver a história: na linha 1, as corridas que tiveram paradas por vedação (vermelho forte) geraram lotes HOLD e REJECT. As próximas consultas transformam essa impressão em números.

## 1. Manutenção × produção: paradas não planejadas por linha e modo de falha"""),
(C, """print(q.DOWNTIME_BY_FAILURE_MODE)
paradas = pd.DataFrame(query(g, q.DOWNTIME_BY_FAILURE_MODE)).astype({"stops": int, "total_min": int})
paradas"""),
(C, """figures.pareto(g); plt.show()"""),
(M, """**Leitura:** "desgaste de vedação" na linha 1 domina (3 paradas, 54 min). O caminho `mfg:occurredOn/mfg:partOf/rdfs:label` vai da parada até a máquina, da máquina até a linha, e da linha até o nome, numa linha só de SPARQL. O almoço (`planned true`) fica fora.

## 2. Manutenção → componente: o que trocar"""),
(C, """pd.DataFrame(query(g, q.COMPONENT_TO_REPLACE))"""),
(M, """O modo de falha aponta para o componente afetado (`mnt:affects`), e a ordem de manutenção `MO-0077` registra a troca do kit de vedação. Em CMMS sem modelo de falha, essa ligação depende de alguém ler o texto livre da ordem.

## 3. Manutenção × produção × qualidade: os lotes feitos durante as falhas"""),
(C, """lotes = pd.DataFrame(query(g, q.LOTS_HIT_BY_FAILURE))
lotes"""),
(M, """**Leitura:** a consulta liga cada corrida às paradas que aconteceram **dentro do intervalo dela** (`?ds < ?re && ?de > ?rs`), e cada lote à sua inspeção.

* `L-1041`: nenhuma parada durante a corrida, 4 vazamentos, **PASS**.
* `L-1042`: uma parada por desgaste de vedação, 37 vazamentos, **HOLD**.
* `L-1043`: três paradas (duas de vedação), 61 vazamentos, **REJECT**.
* Linhas 2 e 3 tiveram paradas por outros motivos e passaram na inspeção.

## 4. Estoque × qualidade: genealogia de um lote de matéria-prima"""),
(C, """gen = pd.DataFrame(query(g, q.GENEALOGY_OF_MATERIAL_LOT))
gen"""),
(M, """Todos os lotes ruins consumiram o lote de tampas **ML-2207** (fornecedor Cap Co). Os lotes da linha 2 e 3 usaram tampas de outro fornecedor e passaram.

## 5. A pergunta difícil: foi a vedação ou foi a tampa?"""),
(C, """historia = lotes.merge(gen[["lot", "material_lot", "supplier", "line"]], on="lot")
historia[["lot", "line", "material_lot", "supplier", "stops_during_run", "failure_modes", "leaks", "result"]]"""),
(M, """**Esta é a lição mais importante do notebook.** O grafo encontrou **duas** explicações plausíveis para os vazamentos e não consegue escolher entre elas:

* **Hipótese A, manutenção:** os vazamentos crescem junto com as paradas por desgaste de vedação (0 → 1 → 2 paradas de vedação, 4 → 37 → 61 vazamentos).
* **Hipótese B, material:** todos os lotes com problema usaram tampas ML-2207, e nenhum lote com outra tampa teve problema.

Os dois fatores estão **confundidos**: a tampa ML-2207 só foi usada na linha 1, que é também a única com desgaste de vedação. Nenhuma consulta resolve isso. O que o grafo faz é **mostrar a pergunta certa em minutos**, em vez de semanas de reunião entre manutenção, qualidade e suprimentos. O próximo passo é um experimento: rodar ML-2207 na linha 2, ou a linha 1 com o kit de vedação novo e outra tampa.

## 6. Energia × produção: kWh por mil peças boas"""),
(C, """energia = pd.DataFrame(query(g, q.ENERGY_PER_PART)).astype({"kwh_per_1000": float, "kwh": float})
energia"""),
(C, """figures.energy(g); plt.show()"""),
(M, """A linha 3 gasta cerca de **80 % mais energia por peça** que a linha 2, fazendo o mesmo produto. O medidor está ligado à **linha** (`nrg:meters`), e as peças estão nas **corridas da máquina** da linha; o grafo soma as corridas por linha e divide. Sem identidade comum, isso seria uma planilha manual.

## 7. Ponte para o UNS: onde assinar"""),
(C, """pd.DataFrame(query(g, q.UNS_TOPICS_FOR_FILLERS))"""),
(M, """O grafo não guarda o valor ao vivo (por enquanto `value` está vazio): ele sabe **onde** o valor está. Uma aplicação pergunta ao grafo "qual o tópico do estado de todas as enchedoras" e assina no broker. O notebook 05 liga essa ponte e preenche `value` em tempo real.

## Resumo

* Consultas que cruzam domínios ficam curtas porque o **tempo** e o **ativo** são comuns a todos os eventos.
* Caminhos de propriedade (`a/b/c`) substituem cadeias de JOIN.
* O grafo **acelera a investigação**, mas não substitui o raciocínio: correlação entre fatores confundidos continua precisando de experimento."""),
])

nb("05_uns_ao_vivo_e_neo4j.ipynb", [
(M, """# 05 · Ligando o grafo ao UNS ao vivo, e exportando para Neo4j

**Objetivo:** duas pontes.

1. **UNS → grafo:** o UNS sabe o **valor atual**; o grafo sabe **o que cada valor é**. O único campo que os une é `mfg:unsTopic`. Uma ponte escuta o broker e atualiza o grafo, criando eventos de mudança de estado.
2. **RDF → Neo4j:** o mesmo grafo convertido em Cypher, para quem usa grafo de propriedades.

Precisa de um broker MQTT em `localhost:1883` (`docker compose up -d`)."""),
(C, SETUP + """
import time, uuid
from lab.uns_bridge import UnsBridge, simulate_plant
from lab import queries as q
import socket
socket.create_connection(('localhost', 1883), timeout=2).close()
print('broker MQTT acessível em localhost:1883')"""),
(M, """## 1. Quantos tópicos o modelo conhece"""),
(C, """g = load_plant()
ponte = UnsBridge(g, prefix=f"estudo-{uuid.uuid4().hex[:4]}")
print(f"{len(ponte.topic_to_dp)} tópicos modelados, por exemplo:")
for t in sorted(ponte.topic_to_dp)[:5]: print("  ", t)"""),
(M, """## 2. Ligando a ponte e simulando 8 segundos de tráfego

O simulador publica estado, velocidade e temperatura das três enchedoras, e **também** uma tag `vibration_rms` que ninguém cadastrou no modelo."""),
(C, """ponte.start(); time.sleep(0.3)
simulate_plant(prefix=ponte.prefix, seconds=8)
time.sleep(0.5); ponte.stop()
print(f"mensagens recebidas      : {ponte.messages}")
print(f"eventos de estado criados: {ponte.events_added}")
print(f"tópicos órfãos           : {list(ponte.orphans)}")"""),
(M, """**Leitura**

* Toda mensagem com tópico conhecido atualizou `lastValue` e `lastUpdate` no nó do ponto de dado.
* Cada **mudança** de estado virou um nó `StateChange` ligado à máquina: o histórico entra no modelo, não fica só no broker.
* `vibration_rms` é um **órfão**: existe no UNS mas não no modelo. Na prática é alguém que adicionou um sensor sem cadastrar o ativo. A ponte não descarta: registra, para alguém decidir se cadastra.

## 3. A mesma consulta do notebook 04, agora com valor ao vivo"""),
(C, """pd.DataFrame(query(g, q.UNS_TOPICS_FOR_FILLERS))"""),
(C, """eventos = query(g, '''
SELECT ?maquina ?estado ?quando WHERE {
  ?e a mfg:StateChange ; mfg:toState ?estado ; mfg:startTime ?quando ; mfg:occurredOn/rdfs:label ?maquina .
} ORDER BY ?quando''')
pd.DataFrame(eventos).assign(quando=lambda d: pd.to_datetime(d.quando).dt.strftime("%H:%M:%S.%f").str[:12])"""),
(M, """Os eventos estão ligados à **máquina**, que está ligada à linha, à planta, às ordens e às paradas. Uma pergunta como "a enchedora da linha 1 entrou em FAULTED durante qual corrida, consumindo qual lote de tampa?" fica a uma consulta de distância.

## 4. Exportando para Neo4j (Cypher)

Mapeamento usado: cada recurso com tipo vira um **nó** com o nome da classe como label, literais viram **propriedades**, e relações entre recursos viram **arestas** em `MAIÚSCULAS`."""),
(C, """from lab.to_cypher import to_cypher
linhas = to_cypher(load_plant(with_ontology=False))
print(f"{len(linhas)} comandos Cypher\\n")
for l in [linhas[0], linhas[1], linhas[60]] + [x for x in linhas if "CAUSED_BY" in x][:1] + [x for x in linhas if "CONSUMED" in x][:1]:
    print(l[:230]); print()"""),
(C, """from collections import Counter
rels = Counter(l.split("-[:")[1].split("]")[0] for l in linhas if "-[:" in l)
pd.Series(rels).sort_values().plot.barh(figsize=(6, 4), color="#2980b9", title="Arestas exportadas por tipo"); import matplotlib.pyplot as plt; plt.show()"""),
(M, """O arquivo pronto está em `neo4j/plant.cypher`. Para carregar: `docker compose -f neo4j/docker-compose.yml up -d`, abrir http://localhost:7474 e colar o arquivo, ou `cypher-shell -f neo4j/plant.cypher`. A mesma pergunta da seção 5 do notebook 04, em Cypher, está em `neo4j/queries.cypher`.

**RDF ou Neo4j?**

| | RDF + SPARQL | Neo4j + Cypher |
|---|---|---|
| Esquema e regras | OWL e SHACL padronizados | convenções do projeto |
| Identidade | IRIs globais, fáceis de juntar entre sistemas | ids locais |
| Consultas de caminho | property paths | padrões visuais, muito legíveis |
| Ecossistema de aplicação | menor | maior, com visualização pronta |

Uma combinação comum: modelar e validar em RDF, publicar para aplicações em Neo4j.

## Resumo

* O **tópico do UNS é a chave** entre o mundo ao vivo e o mundo semântico.
* Eventos de estado gravados no grafo herdam todo o contexto da máquina.
* Tópicos órfãos são um indicador de governança: dados que existem sem significado.
* O modelo é independente da tecnologia: o mesmo grafo vira Cypher com um script."""),
])
nb("06_perguntas_do_modelo_ampliado.ipynb", [
(M, """# 06 · O modelo ampliado: mais domínios, mais evidência

**Objetivo:** a versão 2 da ontologia acrescenta capacidades, estados com transições, planos preventivos, sobressalentes, medições contra especificação, não conformidades, linha de base de energia, fornecedores e estoque. Este notebook mostra **o que cada acréscimo permite perguntar**, e volta à dúvida do notebook 04 (vedação ou tampa?) com evidência nova.

Regra usada para decidir o que entrou no modelo: **nenhuma classe sem uma pergunta de negócio que precise dela**. Cada seção abaixo é uma dessas perguntas."""),
(C, SETUP + """
from lab import queries as q, figures
import matplotlib.pyplot as plt
g = load_plant()"""),
(M, """## 1. Capacidade: em quais linhas cada produto pode rodar?

O núcleo ganhou `Capability` (o que um equipamento **sabe fazer**) e a produção ganhou `requiresCapability` (o que um produto **exige**). Uma linha serve para um produto quando nenhuma capacidade exigida fica sem equipamento que a ofereça."""),
(C, """print(q.LINES_CAPABLE_OF_PRODUCT)
pd.DataFrame(query(g, q.LINES_CAPABLE_OF_PRODUCT))"""),
(M, """**Leitura:** a água de 500 ml roda nas três linhas. O suco de 1 l só roda na **linha 3**, a única com enchedora para garrafa de 1 l e tampadora de 38 mm. Para o planejamento isso significa que uma parada longa da linha 3 bloqueia o suco inteiro.

Repare na técnica da consulta: **dupla negação** (`FILTER NOT EXISTS` dentro de `FILTER NOT EXISTS`). Em português: "não existe capacidade exigida que não seja oferecida". É a forma de escrever "para todo" em SPARQL.

## 2. Preventiva: algum plano estava vencido no dia?"""),
(C, """pd.DataFrame(query(g, q.overdue_plans()))"""),
(M, """**Leitura:** o plano `PM-SEAL-L1` (troca do kit de vedação da enchedora da linha 1, a cada 30 dias) venceu em **28 de outubro**, treze dias antes do turno. E é justamente o componente por trás das três paradas por desgaste de vedação. A manutenção corretiva `MO-0077` trocou o kit **depois** das paradas; a preventiva teria trocado antes.

## 3. Sobressalentes: qual falha vista no turno não tem peça em estoque?"""),
(C, """pd.DataFrame(query(g, q.SPARE_RISK))"""),
(M, """Houve uma parada por sobrecarga de motor, e o sobressalente do motor principal está com **estoque zero**. Hoje foram 9 minutos; se o motor falhar de vez, a parada dura o prazo de entrega da peça. Essa pergunta cruza três coisas que costumam estar em sistemas separados: o histórico de paradas, a árvore de componentes e o almoxarifado.

## 4. Qualidade: o torque das tampas contra a especificação"""),
(C, """torque = pd.DataFrame(query(g, q.TORQUE_VS_SPEC)).astype({"mean": float, "lowest": float, "samples": int, "out_of_spec": int})
torque"""),
(C, """figures.torque(g); plt.show()"""),
(M, """**Leitura:** a especificação pede torque de remoção entre 1,40 e 2,00 N·m. Os lotes que usaram tampas `ML-2210` e `ML-2215` ficam perto de 1,70. Os três lotes com tampa **`ML-2207`** ficam todos na parte de baixo da faixa, e dois deles têm amostras **fora** da especificação (2 de 5 e 4 de 5).

Isso é evidência nova para a pergunta do notebook 04. Vamos juntar tudo.

## 5. De volta à pergunta difícil: vedação ou tampa?"""),
(C, """lotes = pd.DataFrame(query(g, q.LOTS_HIT_BY_FAILURE))[["lot", "result", "leaks", "stops_during_run"]]
quadro = lotes.merge(torque[["lot", "line", "material_lot", "mean", "out_of_spec"]], on="lot")
quadro.rename(columns={"mean": "torque_medio", "out_of_spec": "torque_fora", "stops_during_run": "paradas"})"""),
(M, """**O que mudou em relação ao notebook 04**

| Evidência | Aponta para |
|---|---|
| Vazamentos crescem com as paradas por vedação | enchedora (manutenção) |
| Plano preventivo do kit de vedação vencido há 13 dias | enchedora (manutenção) |
| Todos os lotes ruins usaram a tampa ML-2207 | tampa (material) |
| Torque baixo em **todos** os lotes com ML-2207, inclusive no L-1041, que não teve nenhuma parada | tampa (material) |

A última linha é a mais informativa: o lote `L-1041` rodou **sem parada nenhuma** e mesmo assim tem o torque mais baixo que os lotes das outras linhas. Isso enfraquece a hipótese de que só a vedação explica o problema.

**Mas continua sem veredito.** O torque também depende do cabeçote da tampadora da linha 1, e a ML-2207 só rodou nessa linha. O modelo ampliado **estreitou** as hipóteses e deixou o experimento mais barato: rodar um palete de ML-2207 na linha 2 e medir o torque responde em uma hora. Mais domínios no grafo significam mais evidência, não o fim da necessidade de experimentar.

## 6. Contenção: onde está o resto do material suspeito?"""),
(C, """pd.DataFrame(query(g, q.STOCK_TO_QUARANTINE))"""),
(M, """Enquanto a causa não é confirmada, a ação imediata é **segregar** o material. A consulta parte das não conformidades abertas, sobe pela genealogia até o lote de tampa e desce até o estoque: **13.800 tampas** em dois lugares, uma parte ainda no ponto de uso da linha 1, pronta para entrar na próxima ordem.

## 7. Energia: quem está fora da linha de base?"""),
(C, """base = pd.DataFrame(query(g, q.ENERGY_VS_BASELINE))
base.assign(actual=base.actual.astype(float).round(2), deviation_pct=base.deviation_pct.astype(float).round(1))"""),
(C, """figures.baseline(g); plt.show()"""),
(M, """No notebook 04 vimos que a linha 3 gasta mais por peça. Agora há um **critério**: a linha de base do produto é 3,5 kWh por mil garrafas, com 15 % de tolerância. As linhas 1 e 2 estão dentro; a linha 3 está **64 % acima**. Sem linha de base, "gasta mais" é uma observação. Com ela, é um desvio com dono e prazo.

## 8. Estados: o modelo sabe o que é impossível

O núcleo agora define quatro estados harmonizados e as transições permitidas. Uma máquina em `FAULTED` precisa ser **rearmada** (ir para `STOPPED`) antes de voltar a rodar."""),
(C, """pd.DataFrame(query(g, "SELECT ?de ?para WHERE { ?a a mfg:OperatingState ; rdfs:label ?de ; mfg:canTransitionTo/rdfs:label ?para } ORDER BY ?de ?para"))"""),
(M, """Ligamos a ponte do notebook 05 e deixamos o simulador publicar por 10 segundos. O simulador é ingênuo de propósito: às vezes manda uma máquina de `FAULTED` direto para `RUNNING`."""),
(C, """import socket, time, uuid
socket.create_connection(("localhost", 1883), timeout=2).close()
from lab.uns_bridge import UnsBridge, simulate_plant
vivo = load_plant()
ponte = UnsBridge(vivo, prefix=f"estudo-{uuid.uuid4().hex[:4]}")
ponte.start(); time.sleep(0.3)
simulate_plant(prefix=ponte.prefix, seconds=10, seed=7)
time.sleep(0.5); ponte.stop()
print(f"mudanças de estado registradas: {ponte.events_added}")
ilegais = pd.DataFrame(query(vivo, q.ILLEGAL_TRANSITIONS))
print(f"transições que o modelo considera impossíveis: {len(ilegais)}")
ilegais.assign(when=lambda d: pd.to_datetime(d.when).dt.strftime("%H:%M:%S")) if len(ilegais) else ilegais"""),
(M, """**Leitura:** cada linha é uma mudança que chegou pelo UNS e que **não existe** na lista de transições permitidas. Na prática isso costuma ser um destes problemas: o gateway perdeu uma mensagem intermediária, o CLP mapeia dois estados internos para o mesmo texto, ou a taxa de leitura é lenta demais para ver o rearme. Sem o modelo de estados, esses eventos entrariam no cálculo de disponibilidade sem ninguém perceber.

## 9. Os contratos novos

Cada classe nova que carrega uma regra de negócio ganhou um contrato SHACL. O arquivo `data/broken_v2.ttl` tem cinco registros errados, um por contrato."""),
(C, """from rdflib import Graph
from lab.graph import ROOT
from lab.validate import validate
sujo = Graph().parse(ROOT / "data" / "plant.ttl"); sujo.parse(ROOT / "data" / "broken_v2.ttl")
ok, violacoes = validate(sujo)
print("conforma:", ok, "| violações:", len(violacoes))
pd.DataFrame(violacoes)"""),
(M, """Limites trocados numa especificação, medição em texto, disposição em texto livre, plano sem data, lote sem fornecedor e estoque negativo: todos barrados na entrada, cada um com a mensagem que diz o que corrigir.

## Resumo

* O modelo cresceu guiado por perguntas: **cada classe nova responde a algo** que antes exigia juntar sistemas na mão.
* Mais domínios trouxeram **mais evidência** para a mesma investigação, e mostraram o experimento mais barato.
* Estados com transições deixam o modelo **desconfiar do dado**, e não só guardá-lo.
* O notebook 07 mostra como tudo isso fica legível para uma pessoa nova no projeto e para um agente de IA."""),
])

nb("07_ontologia_legivel_por_agentes.ipynb", [
(M, """# 07 · Uma ontologia que pessoas e agentes de IA conseguem ler

**Objetivo:** um agente de IA que vai consultar o grafo de uma planta tem o mesmo problema de um engenheiro no primeiro dia: não sabe quais classes existem, o que cada uma significa, nem como se ligam. Este notebook mostra como a ontologia responde a isso **sozinha**, e como garantimos que ela continue respondendo.

Quatro peças:

| Peça | Para quê | Onde |
|---|---|---|
| **Definição e exemplo em todo termo** | saber o que cabe em cada classe sem olhar os dados | `ontology/*.ttl` |
| **Catálogo** | consultar o modelo como texto, do tamanho de um prompt | `lab/catalog.py` |
| **Regras da casa (lint)** | impedir que o modelo apodreça em silêncio | `lab/lint.py` |
| **Perguntas de competência** | provar que o modelo responde ao que o negócio precisa | `lab/competency.py` |

Nenhum modelo de linguagem é chamado aqui. O notebook prepara o terreno: as funções abaixo são exatamente as **ferramentas** que um agente receberia."""),
(C, SETUP + """
from lab import catalog, lint, competency"""),
(M, """## 1. O tamanho do modelo"""),
(C, """m = pd.DataFrame(catalog.metrics())
print("total de termos:", m.terms.sum(), "| com definição:", m["with definition"].sum())
m"""),
(M, """Todo termo tem definição. Isso não é capricho: é a primeira regra do lint (seção 4), e é o que torna as próximas seções possíveis.

## 2. Perguntando ao modelo o que é uma coisa

`describe` devolve tudo sobre um termo: definição, exemplos, de quem herda, o que ele tem e quem aponta para ele, **incluindo o que vem das classes mãe**."""),
(C, """print(catalog.describe("Downtime"))"""),
(M, """**Leitura:** só com esse texto dá para escrever uma consulta sobre paradas sem abrir nenhum arquivo. `occurredOn`, `startTime` e `endTime` não foram declarados em `Downtime`: vieram de `mfg:Event`. Um agente que lesse só o arquivo de manutenção não saberia que uma parada tem horário.

Nome incompleto também é tratado, porque agentes (e pessoas) erram nomes:"""),
(C, """print(catalog.describe("Faulted"))
print()
print(catalog.describe("Maintenance"))"""),
(M, """## 3. O modelo inteiro num cartão

`schema_card` gera o modelo como texto compacto. Cabe num prompt e pode ser recortado por módulo."""),
(C, """cartao = catalog.schema_card()
print(f"modelo completo: {len(cartao)} caracteres, cerca de {len(cartao) // 4} tokens\\n")
print(catalog.schema_card(["maintenance"]))"""),
(M, """Com esse cartão no contexto, um modelo de linguagem consegue escrever SPARQL usando os nomes certos de classes e relações, em vez de adivinhar. O cartão é **gerado** dos arquivos `.ttl`: se a ontologia muda, ele muda junto, e não existe documentação paralela para ficar desatualizada.

## 4. Regras da casa: o lint

O que o lint verifica: todo termo com rótulo e definição, toda classe com exemplo, toda propriedade com domínio e contradomínio, toda classe com pelo menos uma instância nos dados de exemplo, e **nenhum termo usado nos dados sem estar declarado**."""),
(C, """print("problemas no modelo atual:", lint.problems())"""),
(C, """# Simulando três descuidos comuns numa cópia do modelo
from rdflib import Graph, Literal, RDF, RDFS, OWL
from lab.graph import ROOT, PRD, MNT
modelo = load_ontology()
modelo.add((PRD.Pallet, RDF.type, OWL.Class)); modelo.add((PRD.Pallet, RDFS.label, Literal("Pallet")))   # classe sem definição, exemplo nem uso
modelo.add((MNT.severity, RDF.type, OWL.DatatypeProperty)); modelo.add((MNT.severity, RDFS.label, Literal("severity")))  # atributo sem nada
dados = Graph().parse(ROOT / "data" / "plant.ttl")
dados.add((ID["downtime/D-001"], MNT.rootCause, Literal("operador disse que foi a vedação")))            # predicado inventado na integração
for p in lint.problems(modelo, dados): print(" -", p)"""),
(M, """**Leitura:** o lint pegou a classe sem definição e sem uso, o atributo sem domínio nem contradomínio, e o caso mais traiçoeiro: `mnt:rootCause`, um predicado que **não existe na ontologia** mas apareceu nos dados. Em RDF nada impede isso; o dado entra, e ninguém mais sabe que ele existe. O lint roda no CI, então um pull request com qualquer um desses descuidos não passa.

## 5. Perguntas de competência

Uma pergunta de competência é uma pergunta de negócio escrita **antes** do modelo, usada para decidir o que entra nele e, depois, para provar que ele é suficiente. Aqui cada uma tem a consulta que a responde e uma verificação do resultado."""),
(C, """cq = pd.DataFrame(competency.run())
print(f"{cq.answered.sum()} de {len(cq)} perguntas respondidas")
cq[["id", "question", "modules", "answer"]]"""),
(M, """**Por que isso importa:** se alguém renomear uma relação ou remover uma classe, a pergunta correspondente deixa de ser respondida e o teste diz **qual pergunta de negócio foi perdida**, não só "um teste falhou". A coluna `modules` mostra que quase todas cruzam mais de um domínio, que é a razão de existir do grafo.

## 6. A ontologia dentro do Neo4j

Na exportação para Neo4j (notebook 05) iam só os dados. Agora o próprio modelo vai junto, como nós: cada classe vira um nó com definição e exemplos, e cada instância aponta para a sua classe."""),
(C, """from lab.to_cypher import ontology_to_cypher
linhas = ontology_to_cypher()
print(len(linhas), "comandos\\n")
amostra = [linhas[1]] + [x for x in linhas if "SUBCLASS_OF" in x][:1] + [x for x in linhas if "[:DOMAIN]" in x][:1] + [x for x in linhas if "CAN_TRANSITION_TO" in x][:1] + [linhas[-1]]
for l in amostra:
    print(l[:260]); print()"""),
(M, """Com o modelo no banco, quem consulta o Neo4j pode perguntar primeiro **o que existe e o que significa**, e só depois buscar as instâncias:

```cypher
// o que é um Downtime e o que posso seguir a partir dele?
MATCH (c:OntologyClass {name: 'Downtime'})-[:SUBCLASS_OF*0..]->(k)<-[:DOMAIN]-(p:OntologyProperty)
RETURN c.definition, p.name, p.definition;

// todas as instâncias de qualquer tipo de evento
MATCH (n)-[:INSTANCE_OF]->(:OntologyClass)-[:SUBCLASS_OF*0..]->(:OntologyClass {name: 'Event'}) RETURN n LIMIT 25;
```

## 7. Como um agente usaria isto

O roteiro abaixo imita o ciclo de um agente investigando "por que o lote L-1043 foi reprovado?". **Aqui quem decide o próximo passo é o roteiro**; num agente de verdade seria um modelo de linguagem. O que interessa é ver que cada passo só usa as ferramentas deste notebook."""),
(C, """from IPython.display import display
from lab import queries as q
g = load_plant()

def ferramenta_descrever(termo): return catalog.describe(termo)
def ferramenta_consultar(sparql): return pd.DataFrame(query(g, sparql))

passos = [
    ("O que é um lote e o que se liga a ele?", lambda: print(ferramenta_descrever("Lot"))),
    ("Quem inspecionou o lote e o que decidiu?", lambda: display(ferramenta_consultar(q.LOTS_HIT_BY_FAILURE).query("lot == 'L-1043'"))),
    ("A inspeção se liga a medições. O que é uma medição?", lambda: print(ferramenta_descrever("Measurement"))),
    ("Como ficou o torque desse lote contra a especificação?", lambda: display(ferramenta_consultar(q.TORQUE_VS_SPEC).query("lot == 'L-1043'"))),
    ("O lote veio de uma corrida que consumiu material. Onde está o resto?", lambda: display(ferramenta_consultar(q.STOCK_TO_QUARANTINE))),
]
for i, (pensamento, acao) in enumerate(passos, 1):
    print(f"\\n--- passo {i}: {pensamento}")
    acao()"""),
(M, """Cada passo fez uma de duas coisas: **ler o modelo** para saber o que existe, ou **consultar os dados** usando o que acabou de ler. É esse vaivém que um agente faz, e ele só funciona se o modelo tiver definições, se o catálogo existir e se as consultas tiverem resposta conhecida para comparar.

## Resumo

* **Definição e exemplo em todo termo** transformam a ontologia em documentação que não desatualiza.
* O **catálogo** entrega o modelo como texto, por termo ou inteiro, no tamanho de um prompt.
* O **lint** impede os três descuidos clássicos, inclusive o termo usado nos dados sem ter sido declarado.
* As **perguntas de competência** dizem o que o modelo precisa responder, e viram teste.
* Tudo isso é a base de um agente que investiga com trilha auditável, que é o próximo projeto."""),
])
print("ok")
