# Calorvia — laboratoire 2 : Text-to-SQL

**Checkpoint 15 — Journal et catalogue du routeur vérifiés sur le Z4. Le carnet utilise `http://127.0.0.1:8002/v1` et `calorvia_qwen`. La première génération via ce routeur reste à vérifier.**
Reprendre ici et dans `CHECKPOINT.json`, sans recréer les données. Branche de
travail conservée : `feat/text2sql-calorvia`. Les étapes sont sauvegardées environ
toutes les 15 minutes par des commits limités au laboratoire 2.

## Architecture en service et première question

Le carnet appelle l’agent LangGraph. Il ouvre un serveur MCP local par entrée/sortie standard et présente les six outils à Qwen via une API locale compatible OpenAI. Qwen propose les appels. Le serveur MCP valide le SQL et interroge les sources avec `agent_ro`. Les résultats reviennent au modèle pour la rédaction de la réponse. L’API FastAPI du laboratoire (port prévu 9001) constitue une autre entrée vers le même agent.

| Base | Serveur du Z4 | Rôle et contenu |
|---|---|---|
| GESPRO | SQL Server 14330 | 23 tables ERP, notamment VTE_FACT et VTE_FACT_LIG |
| compta | PostgreSQL 5433 | 14 tables comptables, dont ecriture et ligne_ecriture |
| paie | PostgreSQL 5434 | 14 tables de paie, dont payslips et payslip_lines |
| calorvia_text2sql_journal | PostgreSQL 5433 | Base distincte sur le même serveur que compta. Le compte text2sql_writer écrit les événements et expériences dans le schéma text2sql_journal. |

Le catalogue décrit les 51 tables métier. L’ontologie ajoute les définitions métier. Sa compilation NVIDIA réelle et sa certification humaine restent à effectuer. Le test courant utilise Qwen seul pour la génération, sans ontologie. BGE-M3 sur 8000 fournit des embeddings au workflow d’ontologie. Le routeur partagé répond sur le port 8002. Le carnet consulte son catalogue avant la question. Au contrôle du Z4, Gemma était chargé et Qwen déchargé. Les comptages natifs constituent les références de vérification.

## Coexistence avec le RAG

Avant chaque changement ou commande susceptible d’affecter le RAG, comparer `origin/main` et `origin/feat/text2sql-calorvia` depuis leur ancêtre commun dans les deux sens. Examiner les chemins modifiés ainsi que les dépendances, ports, volumes, collections, résultats et endpoints de modèles touchés par l’étape. Avant une intégration sur le Z4, vérifier les fichiers locaux avec `git status --short` et effectuer un essai de fusion avec `git merge-tree --write-tree` sur les références actualisées. Les révisions du dernier contrôle figurent dans `CHECKPOINT.json`.

## Destination vérifiée

L'énoncé intégral est `data/text2sql/projet_text2sql_enonce.md`. Guide, présentation,
Compose et trois scripts SQL se trouvent dans `data/text2sql/sources_calorvia/`.
Les PDF de paie ne sont pas présents ici ; leur lecture est facultative et n'est
pas utilisée. La réserve du formateur n'a pas été consultée.

| Exigence obligatoire | Test d'acceptation | État |
|---|---|---|
| Trois bases : GESPRO/SQL Server, compta/PostgreSQL, paie/PostgreSQL | agent_ro ; 10 185 factures, 20 562 écritures, 7 298 fiches | Lectures natives sur le Z4 : 10 185 factures, 20 562 écritures et 7 298 fiches |
| Ontologie NVIDIA auto-ontology | Génération réelle, export YAML des 51 tables et liens ; définitions testées et certifiées humainement | Brouillon natif, graphes et protocole testés ; génération et certification en attente |
| Comparer ≥2 solutions pour SQL Server | Note argumentée Trino / copie / import YAML | Dans RAPPORT.md ; import YAML retenu sous réserve du test natif |
| Six outils MCP | list_sources, list_tables, get_table_card, find_values, validate_sql, execute_sql | Découverte stdio et validation testées ; accès natifs en attente |
| Lecture seule à plusieurs niveaux | SELECT unique, dialecte, noms, limites ; ACL refusant l'écriture même validation contournée | Tests applicatifs passés ; 4 contrôles natifs réussis sur le Z4 |
| Agent LangChain/LangGraph ou n8n | Choix des sources, corrections bornées, rapprochement, refus/clarification, SQL exécuté montré | LangGraph et Decimal testés avec modèle simulé ; vrai LLM en attente |
| API OpenAI | GET /v1/models ; POST /v1/chat/completions | SDK officiel, JSON et SSE testés avec réponse simulée |
| ≥40 questions et attentes | Simples, croisées, ambiguës, impossibles, malveillantes | 45 questions ; 37 requêtes de référence vérifiées sur données fournies |
| Comparaison sans/avec ontologie | Même commit/modèle/données/réglages ; exactitude, validité SQL, erreurs, comportements, latence | Évaluateur séquentiel et reprenable prêt ; campagnes non exécutées |
| Journal PostgreSQL et export results/ | Question, SQL, source, durée, volume, erreurs, résultats d'expériences et commit | Schéma distinct ; DSN ou transport Docker existant ; exécution native en attente |
| Dépôt privé text2sql-calorvia, collaborateur, tags | Historique authentique, README, tags v0.1-sources à v1.0 | Développement dans le dépôt RAG ; remise distincte en attente |
| Rapport et démonstration | RAPPORT.md, cinq échecs réels analysés ; cinq questions du formateur en dix minutes | Rapport provisoire et DEMO.md préparés ; résultats/démo réels en attente |

Facultatif : graphiques, mémoire persistante, autres outils, comparaison de modèles,
Trino. Le SSE renvoie la réponse après son calcul ; il ne diffuse pas les tokens
internes. L'historique client est accepté, sans mémoire persistante supplémentaire.

## Installation et exécution

Depuis la racine du dépôt, utiliser le Python de l'environnement **RAG existant**.
Si les dépendances ne sont pas encore disponibles, le diagnostic initial ne
requiert que la bibliothèque standard ; il n'affiche pas les secrets :

```bash
.venv/bin/python text2sql/local_check.py
.venv/bin/python -m text2sql dependencies
```

`dependencies` compare les versions sans rien installer. `dependencies --install`
ajoute les paquets manquants en contraignant toutes les versions déjà présentes ;
il refuse un conflit. Ne pas lancer de synchronisation globale. Après tout ajout
sur le poste réel, relancer les tests Task 2 et un échange connu de Task 1 avant
une campagne. Aucun changement de dépendance partagé n'a été effectué ici.

Configurer `text2sql/.env` d'après `.env.example`, sans remplacer le `.env` du RAG.
Le LLM reprend `CALORVIA_LLM_BASE_URL/MODEL` ou les paramètres explicites T2SQL.
Le mot de passe agent_ro et le journal doivent rester sur le poste. Le port ERP
réel du Compose fourni est **14330**, malgré les mentions 1433 dans le guide.

```bash
.venv/bin/python -m text2sql preflight
.venv/bin/python -m pytest text2sql/tests -q
# Après la cellule de préparation du journal, dans chaque nouveau terminal :
set -a
. data/text2sql/journal_z4.env
set +a
.venv/bin/python -m text2sql init-journal
.venv/bin/python -m text2sql verify-sources
T2SQL_LIVE=1 .venv/bin/python -m pytest text2sql/tests/test_live_permissions.py -q
.venv/bin/python -m text2sql native-check
```

Après inventaire, démarrer les sources une par une. Pour la comptabilité sur le Z4 :

```bash
.venv/bin/python text2sql/restore_postgres.py ~/labo/calorvia_t2sql/sources_calorvia/docker compta
```

Le script conserve les identifiants locaux dans le `.env` Docker et limite la publication au loopback. Le contrôle TCP utilise `agent_ro`. Le même script avec `paie` a vérifié les 7 298 fiches avec `agent_ro` en transaction de lecture seule. Pour GESPRO, utiliser `.venv/bin/python text2sql/restore_erp.py ~/labo/calorvia_t2sql/sources_calorvia/docker` entre deux lots RAG. Le script limite la mémoire interne du nouveau moteur à 2 048 Mo, garde le port 14330 sur loopback et appelle le service officiel avec FORCE_RESTORE=0. Les trois bases natives et leurs ACL exigent des preuves distinctes.

### Ontologie

Le code NVIDIA est épinglé au commit indiqué dans `auto_ontology.py`. Son code,
`.env.example`, ses schémas et ses routes API ont été relus. Ses dépendances
`openai==2.44.0` et `langchain-openai<1.3.5` sont incompatibles avec le banc CPU
utilisé ici (3.55.1 et 1.8.3). La préparation prévoit donc des services CPU isolés,
sans modèle GPU supplémentaire, et un catalogue pgvector distinct dont les
migrations ne touchent pas le schéma du cours. Le poste utilise langchain-openai 1.8.1, au-dessus de la borne NVIDIA.

```bash
.venv/bin/python -m text2sql ontology-draft
.venv/bin/python -m text2sql serve
```

Dans un autre terminal, après avoir réservé un créneau libre hors des évaluations RAG :

```bash
.venv/bin/python -m text2sql ontology-prepare
.venv/bin/python -m text2sql ontology-start --allow-inference
.venv/bin/python -m text2sql ontology-generate --allow-inference
```

Cette préparation ne lance aucun serveur de modèle. Les quatre rôles NVIDIA
pointent vers les endpoints locaux ; KumoRFM est désactivé. Un adaptateur lexical
CPU au format NIM est disponible sur l'API Task 2 ; il ne remplace pas BGE sous un
nom trompeur. La compatibilité réelle des sorties structurées, embeddings et de
la compilation doit encore être établie. Ne pas présenter le brouillon YAML comme
un export généré/certifié. Le reçu réel, ses empreintes et la couverture sont
contrôlés avant l'expérience avec ontologie. Un reçu de test simulé est refusé.

### Évaluation, reprise et démonstration

Travailler dans un worktree propre pour les campagnes officielles, afin de
préserver les modifications RAG non commitées. Le worktree utilise les mêmes
endpoints de modèles et sources ; ne pas recréer leur infrastructure. Les fichiers
.env locaux doivent y être disponibles sans être ajoutés à Git.

```bash
.venv/bin/python -m text2sql evaluate --without-ontology --allow-inference
.venv/bin/python -m text2sql evaluate --allow-inference
.venv/bin/python -m text2sql compare --without-run data/text2sql/runs/SANS.json --with-run data/text2sql/runs/AVEC.json
.venv/bin/python -m text2sql evaluate --resume data/text2sql/runs/LOT_INTERROMPU.json --allow-inference
```

Avant les deux campagnes, vérifier et commiter le reçu NVIDIA, son export et les références natives du même instantané. Les deux campagnes utilisent ensuite ce commit. Les fichiers de travail JSON/CSV sont dans `data/text2sql/runs/`. Pour la remise, copier les deux lots terminés et leurs CSV relus dans `text2sql/results/` après la comparaison. Utiliser les noms réels affichés par la commande.
Une sauvegarde atomique JSON et une écriture PostgreSQL suivent **chaque question**.
La reprise refuse tout changement de commit, modèle, données ou paramètres.
Les questions attendues ne sont jamais injectées dans le contexte de l'agent.
Les nombres tolèrent 0,01 pour les montants ; période, unités, regroupements et
refus exigent aussi la revue sémantique dans le CSV. Un contrôle numérique seul
n'est pas un score d'exactitude validé. La comparaison garde les erreurs et valeurs
manquantes visibles. Voir RAPPORT.md et DEMO.md pour le rendu restant.

## Carte des fichiers

| Fichier/module | Rôle | Entrées/dépendances | Sorties et utilisateurs | Exécution/contrôle | Attendu et statut réel |
|---|---|---|---|---|---|
| config.py | Configuration locale | Environnement et .env | Settings pour agent/MCP/API | preflight | Aucun endpoint distant ; testé |
| catalog.py, ontology/catalog.json | Catalogue des DDL | Trois SQL officiels, sqlglot | 51 fiches pour MCP/ontologie | tests/test_workflow.py | Types, PK/FK, commentaires ; vérifiés contre les fichiers |
| validation.py | SELECT borné et confidentialité | SQL, dialecte, catalogue | SQL validé vers sources.py | tests/test_safety.py | Écritures, noms inconnus, fonctions dangereuses refusés ; testé |
| sources.py | Accès agent_ro et rollback | Pilotes natifs, Settings, Journal | Colonnes/lignes/troncature vers MCP | verify-sources, native-check | Code vérifié ; moteurs réels non testés |
| Text2SQL_travail.ipynb | Journal dédié et première question | Python du labo, PostgreSQL compta 5433, routeur Qwen 8002 | Schéma et trace JSON dans data/text2sql/ | Cellules 1, 2 puis 3 hors lot RAG | Journal et catalogue vérifiés sur le Z4 ; inférence en attente |
| journal.py, journal.sql | Traçabilité dédiée | DSN local ou Docker existant | Schéma text2sql_journal | init-journal | Écriture de contrôle annulée avec text2sql_writer sur le Z4 |
| mcp_server.py | Six outils stdio | SourceService | Outils pour agent.py | tests/test_protocol.py | Échange MCP réel sans bases ; passé |
| agent.py | Boucle LangGraph et rapprochement | LLM HTTP, MCP, ontologie | Réponse, SQL, traces et Decimal vers API/évaluation | ask --question «…» | Boucle/rapprochement simulés passés ; LLM réel en attente |
| api.py | Façade OpenAI authentifiée | Agent, clé API | JSON/SSE vers SDK/Open WebUI | serve, tests/test_protocol.py | SDK officiel JSON/SSE et rerank CPU passés |
| ontology.py, ontology/business.yaml | Règles métier et contexte | Définitions corrigées, YAML NVIDIA éventuel | Contexte agent et termes des fiches | tests/test_ontology.py | Pas de fuite de termes dans le mode sans ontologie ; testé |
| auto_ontology.py, ontology/native_draft.yaml | Import/compilation/export NVIDIA | Métadonnées, règles, API locale | Export et reçu vérifiable vers agent/évaluation | ontology-draft / ontology-generate | 51 tables, 80 FK, 9 concepts ; protocole simulé passé, génération réelle en attente |
| ontology_runtime.py | Préparation CPU NVIDIA | Commit officiel, endpoints existants | Configuration privée dans data/text2sql | ontology-prepare/start/stop | Pas de nouveau modèle ; Docker non exécuté ici |
| runtime.py | Exclusion des traitements Task 2 | Verrou local interprocessus | API, agent, compilation, évaluation | tests/test_workflow.py | Concurrence Task 2 refusée ; ne détecte pas Task 1 |
| offline.py | Copies de vérification CPU | SQL officiels, DuckDB, empreintes | data/text2sql/offline vers références | offline-build / offline-check | 457 965 lignes ; copies et références vérifiées |
| evaluation.py, evaluation/questions.json | Jeu et campagnes reprenables | 45 questions, réponses attendues séparées, agent | JSON/CSV et journal PostgreSQL | evaluate / compare | 37 références CPU passées ; aucune mesure LLM réelle |
| restore_erp.py | Démarrage et lecture ERP | Docker, .env du cours, sqlcmd, pymssql | GESPRO et compte de factures | Commande ERP ci-dessus | Contrôle Z4 réussi avec agent_ro, 10 185 factures |
| restore_postgres.py | Restaurer une source PostgreSQL | Compose officiel, .env privé, Docker et psycopg | Volume compta ou paie et contrôle SQL local | Voir commande ci-dessus | Compta et paie vérifiées sur le Z4 |
| local_check.py | Diagnostic avant installation | Bibliothèque standard, état local | data/text2sql/local_environment.json | python text2sql/local_check.py | Aucun secret affiché, aucune inférence |
| preflight.py, cli.py, __main__.py | Commandes et diagnostic après installation | Modules Task 2 et paquets installés | État et contrôles opérateur | python -m text2sql --help | CLI et diagnostic exécutés ici |
| tests/ | Contrats et ACL indépendantes | Données officielles optionnelles ; moteurs pour ACL | Résultats de tests | pytest text2sql/tests -q | 65 tests CPU réussis, dont une interruption/reprise simulée ; 4 tests natifs réussis séparément sur le Z4 |
| CHECKPOINT.json, results/ | Reprise et preuves | État vérifié, résultats distincts de Task 1 | Continuation et rapport | Lire avant de reprendre | État sauvegardé par étape ; aucun score RAG réutilisé |

## Limites et prochaine intervention

D’après les sorties de terminal transmises par Mi, le diagnostic utilisait `~/labo/calorvia_rag/.venv/bin/python` (3.12.14). Les scripts fournis sont sous `~/labo/calorvia_t2sql/sources_calorvia/sql/`. Les ports 14330, 5433 et 5434 ne répondaient pas. Le PostgreSQL du RAG répondait sur 5432.

| Service sur le poste | Sortie communiquée par Mi | Réglage du laboratoire 2 |
|---|---|---|
| BGE-M3 | GET /v1/models sur 8000, HTTP 200 | Embeddings locaux sur 8000 |
| Qwen3.5-9B, GGUF Q4_K_XL | GET /v1/models sur 8002, HTTP 200 | Alias calorvia_qwen disponible, déchargé lors du contrôle. Appel d’outil à vérifier |
| Service sur 9000 | GET /v1/models, HTTP 400. Identité inconnue | Laisser ce port au service existant |
| API Text-to-SQL | Port proposé 9001, disponibilité à vérifier | `T2SQL_API_PORT` règle à la fois FastAPI et l'URL de reranking de NVIDIA |

Le Z4 a exécuté les tests CPU. La mise en service de l’agent avec les bases natives reste à vérifier. Les appels GET ci-dessus lisent les catalogues des services qui répondaient déjà. Les 65 tests et les 37 requêtes de référence ont été exécutés dans l’environnement de vérification de l’IA. Le test de reprise interrompt un modèle simulé dans un dépôt temporaire. Aucune évaluation Qwen ni mesure de précision sur le Z4 n’est disponible.

La PR nº 2 a intégré le checkpoint 2 dans `main` au commit `47a4f45`. La suite est sur `feat/text2sql-calorvia`. Le travail RAG en cours garde la priorité sur les ressources du poste. Mi a installé les six ajouts prévus dans le Python partagé du Z4. L'audit final donne zéro dépendance manquante et zéro incompatibilité. Le comptage RAG sur `rappel_aeris12` renvoie 214 lignes avant et après. Le défaut de décodage JSON de `statuts_rappel` sur plusieurs lignes existait avant cette installation. Mi a exécuté la suite sur le Z4 au commit `47a4f45` avec `T2SQL_LIVE=0`. Quatre contrôles de permissions étaient désactivés. Le test du catalogue et du cache a ignoré le dossier externe, car il cherche les SQL sous `data/text2sql/sources_calorvia/sql`. Le contrôle séparé sur le Z4 a confirmé que les trois scripts du dossier externe correspondent au catalogue, empreintes comprises : 23 tables ERP, 14 en comptabilité, 14 en paie. Avant restauration, l’inventaire du Z4 indiquait Compose 5.7.0, aucun .env Docker, aucun conteneur ou volume correspondant et aucun port source en écoute. Ensuite, le script du commit `1df335d` a vérifié `ecriture=20562` sur compta avec `agent_ro` et `transaction_read_only=on`. La lecture a utilisé psycopg directement. Les trois restaurations sont confirmées par des lectures natives avec agent_ro. Mi a exécuté les quatre tests indépendants des permissions sur le Z4. Les trois bases ont refusé les écritures testées et la base de paie a refusé la lecture du numéro national. La question via MCP et Qwen reste à vérifier. Configurer les identifiants précis des modèles indiqués dans `.env.example` dans le seul environnement du laboratoire 2.

L’IA a préparé le code et les tests. Mi a exécuté les commandes sur le Z4. Cette exécution guidée est consignée séparément de l’évaluation de ses compétences en autonomie. La certification humaine, les cinq échecs réellement
observés et la démonstration avec le formateur restent à effectuer.
