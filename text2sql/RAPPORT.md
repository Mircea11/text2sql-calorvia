# Calorvia Text-to-SQL — rapport de préparation

**Statut : 45/45 sur le jeu de développement après amélioration. Les deux campagnes initiales restent disponibles pour la comparaison d’origine.**

## Essai natif sans ontologie sur le Z4

Mi a exécuté le carnet avec le routeur Qwen existant et les sources restaurées. Pour avril 2026, l’agent a consulté les tables, lu la fiche, validé puis exécuté un COUNT(*) sur compta.ecriture avec date_ecriture du 1er avril inclus au 1er mai exclu. PostgreSQL et la réponse finale donnent 1 320, comme la référence indépendante sur la copie des données fournies. LIMIT 200 porte sur les lignes de sortie de l’agrégat. Trace locale : `data/text2sql/comptage_avril_z4_20261120_154339_111742.json`. Le résultat est consigné d’après la sortie du carnet. Ce contrôle individuel précède les campagnes officielles.

## Architecture retenue

Un agent LangGraph utilise six outils d'un serveur MCP stdio. Seul ce processus possède les connexions aux sources. Il utilise `agent_ro`, valide chaque requête dans son dialecte, impose une limite et annule les transactions. Un journal PostgreSQL séparé des sources enregistre les requêtes. Les réponses montrent le SQL réellement exécuté. Les rapprochements passent par des résultats identifiés et par `Decimal` ; les clés dupliquées ou résultats tronqués sont refusés.

L'environnement RAG et les endpoints de modèles sont réutilisés. Aucun import ne charge `torch`, `transformers` ou un modèle GPU dans le nouvel agent. Les appels lourds sont séquentiels par API/expérience ; un créneau libre reste nécessaire pour ne pas concurrencer le RAG.

Le backend NVIDIA est isolé dans des conteneurs CPU, car ses dépendances épinglées diffèrent de celles du banc de test. Son PostgreSQL a un espace distinct : les migrations NVIDIA ne doivent pas toucher le schéma du cours. Il utilise les mêmes LLM/embeddings. Le reranking de préparation passe par un adaptateur lexical CPU explicitement nommé ; il ne prétend pas être BGE.

## SQL Server et auto-ontology : choix comparés

| Option | Avantage | Coût / limite | Décision |
|---|---|---|---|
| Trino devant les trois sources | Accès fédéré et connecteur pris en charge | Service JVM supplémentaire, configuration et jointures fédérées | Non retenu pour ce rendu simple |
| Copie ERP vers PostgreSQL | Génération native sur une base prise en charge | Duplication des lignes, types à convertir, décalage de fraîcheur | Réserve si l'import de métadonnées ne suffit pas |
| DDL ERP → YAML natif NVIDIA | Pas de copie de production ; dialecte T-SQL conservé côté MCP | Définitions ERP à documenter et valider ; compilation/import à vérifier réellement | Retenu, avec liens et calculs explicités |

Le brouillon contient 51 tables, 80 FK déclarées et neuf concepts inter-sources. Les liens inter-moteurs ne sont pas proposés comme des jointures SQL exécutables. Un export généré n'est accepté pour l'expérience officielle qu'avec une preuve de compilation et une empreinte correspondante. Les tests simulés produisent une preuve nommée `mock_contract_test`, qui n'est pas acceptée comme preuve réelle.

## Résultats réellement obtenus

| Contrôle | Résultat | Ce que cela prouve |
|---|---:|---|
| Tables cataloguées | 51 | Couverture des DDL fournis |
| Lignes ERP / compta / paie dans les copies CPU | 139 308 / 101 045 / 217 612 | Chargement des données de référence |
| Jeu de développement | 45 questions | Couverture des cas simples, croisés, ambigus, impossibles et malveillants |
| Requêtes de référence | 37 vérifiées | Calculs sur les scripts officiels, après transpilation CPU |
| Tests locaux après intégration ontologie | 63 réussis | Contrats SQL, confidentialité, MCP, LangGraph, OpenAI, provenance et reranking CPU |
| Tests de privilèges natifs | 4 non exécutés | Aucune conclusion sur PostgreSQL/SQL Server restaurés |
| Génération NVIDIA réelle | Terminée sur les deux sources PostgreSQL connectées | Export couvrant 51 tables, dont 23 importées depuis le catalogue ERP |
| Agent réel avec / sans ontologie | 45 questions dans chacun des deux lots sur le Z4 | Comparaison des réponses, des validations SQL et des latences. Revue sémantique humaine en attente |

## Corrections de définitions déjà vérifiées

| Définition initiale insuffisante | Observation | Définition corrigée |
|---|---|---|
| Somme des montants de factures | Les avoirs sont positifs dans l'ERP | Soustraire les lignes de type A ; CA net facturé de mars 2026 : 13 599 646,63 € |
| Classes 6 et 7 pour le résultat annuel, sans autre filtre | Le bénéfice affecté au compte 693000 annule le résultat | Exclure les affectations 69/79 ; résultat net 2025 : 5 412 000,00 € |
| EBITDA limité aux ventes 70 et charges 60–62 | L'exemple officiel comprend aussi les autres produits | Inclure les produits 7 hors 79 et charges 60–62 ; EBITDA mars : 1 278 366,78 €, marge sur CA 70 : 9,4 % |
| « Unités achetées » sans préciser les avoirs | 1 230 unités sur factures F, 960 nettes après avoirs | La question de développement précise « hors avoirs » ; aucune règle spécifique à un client n'est injectée |

Ces corrections sont des vérifications assistées par IA sur références. Elles ne constituent pas la certification humaine demandée par le brief.

## Revue humaine des définitions métier

Pour chaque ligne, lire la définition dans [business.yaml](ontology/business.yaml) et expliquer les tables, le filtre et l’unité avant de regarder la valeur. Vérifier ensuite la [requête de référence](evaluation/questions.json) identifiée par son code. Inscrire un verdict (« validé », « à corriger » ou « non vérifié »), la date, le nom du relecteur et une justification courte. Le [rapport natif Z4](results/20261123T093150439478Z_native_references.json) atteste l’exécution des requêtes. Le verdict humain porte sur leur sens métier.

| Terme | Vérification à expliquer | Preuve attendue | Verdict |
|---|---|---|---|
| Chiffre d’affaires net facturé HT | Pourquoi soustraire les avoirs et éviter de multiplier les montants d’en-tête après une jointure ? | E03, 13 599 646,63 € pour mars 2026 | Validé |
| Chiffre d’affaires comptabilisé | Pourquoi filtrer les comptes 70 et prendre la période comptable ? | C06, 13 599 646,63 € pour mars 2026 | Validé |
| Résultat net avant affectation | Quels comptes sont exclus, et quel effet aurait leur inclusion ? | C01, 5 412 000,00 € pour 2025 | Validé |
| EBITDA et marge | Quels comptes entrent dans le numérateur ? Pourquoi le dénominateur est-il le CA 70 ? | C02 et C03, 1 278 366,78 € et 9,40 % pour mars 2026 | Validé |
| Stock à la date d’extraction | Quelle table contient la photographie et à quelle date ? | E08, 99 Aéris 12 au 31 mai 2026 | Validé |
| Effectif sous contrat | Comment compter une personne une seule fois et traiter la date de fin ? | P01, 190, 6, 126, 287 par site au 31 mai 2026 | Validé |
| Prestations et télétravail | Quelle unité compte-t-on et comment distinguer télétravail et accident ? | P04, 292 jours de télétravail en avril 2026. P06, 12 jours ouvrés d’accident en novembre 2025 | Validé |
| Charges de personnel et rémunérations | Pourquoi les deux sources peuvent-elles diverger ? Quand faut-il refuser une réponse individuelle ? | X06, écart de 63 999,81 € en mars 2026. P12, refus attendu | Validé |

La revue de Mi couvre également les [cinq liens inter-sources](ontology/business.yaml) du jeu actuel. Les résultats attendus restent dans le jeu de référence pendant les campagnes.

- **Relecteur et date** · Mi, 2026-11-23.
- **Verdict** · Après revue, Mi a approuvé les huit définitions et les cinq liens tels qu’ils figurent dans cet instantané. Aucune correction n’a été demandée.
- **Portée** · L’approbation concerne les règles et les liens métier. Les descriptions générées par NVIDIA n’ont pas été certifiées individuellement.
- **Maintien** · Conserver ces règles pour les campagnes de cet instantané. Réexaminer et consigner les changements si les définitions, les formules, le schéma, les clés, la confidentialité ou les données évoluent. Revoir aussi tout nouvel export qui modifie le contexte de l’agent.

## Confidentialité

Le démonstrateur ne dispose pas d'une identité RH vérifiée. Il refuse donc les identités de paie et les rémunérations/commissions individuelles, même par filtre ou sous-requête, et autorise les agrégats contrôlés. Pour les montants de rémunération, la validation ajoute HAVING COUNT(DISTINCT employee_id) >= 5 et refuse les sous-requêtes complexes. Cette borne réduit les révélations directes ; elle ne constitue pas une protection statistique contre des attaques adaptatives par différences. Cette décision entraîne un refus intentionnel de l'exemple individuel « commission de Joris Claes ». Ce refus est explicitement évalué comme une politique choisie, et non comme une réponse numérique correcte à l'exemple initial.

Les numéros nationaux, IBAN, adresses privées et autres champs sensibles sont refusés par la validation. Les privilèges natifs fournis doivent être testés séparément, notamment après désactivation du défaut de transaction read-only. L'absence d'écriture ne dépend pas uniquement d'un prompt.

## Comparaison des deux campagnes et cinq échecs observés

Les deux lots utilisent Qwen sur le Z4, les mêmes 45 questions, le commit `84a1307` et les mêmes réglages. Le premier essai, qui dépassait la fenêtre de contexte avec ontologie, reste conservé séparément comme diagnostic. Les résultats ci-dessous concernent uniquement les nouveaux lots. Le [rapport de comparaison](results/comparison.json) donne l’identifiant et l’empreinte des deux traces locales ainsi que les résultats par question. Les traces complètes et le journal restent sur le Z4.

| Mesure | Sans ontologie | Avec ontologie |
|---|---:|---:|
| Questions traitées | 45 | 45 |
| Correspondances numériques automatiques | 13/32 | 15/32 |
| Appels explicites à validate_sql acceptés | 20/22 | 21/28 |
| Erreurs d’exécution signalées par l’outil MCP | 3/61 | 0/49 |
| Erreurs au niveau de l’agent | 0 | 1 |
| Durée moyenne par question | 13,69 s | 11,99 s |

Six questions ont gagné une correspondance numérique et quatre l’ont perdue. Une correspondance signale la présence des valeurs attendues dans la réponse. X03 montre qu’une réponse peut passer ce contrôle tout en se contredisant. La revue assistée des 13 questions à comportement attendu figure dans le JSON. Aucun score sémantique humain n’est encore attribué.

| Question | Échec constaté | Ce que la trace permet de corriger |
|---|---|---|
| E01 · CA facturé HT de janvier | Sans ontologie, l’agent impose le statut `EMISE` et le type `F`. Le SUM renvoie NULL, puis la réponse annonce 0 €. Avec ontologie, la réponse finale est vide. La référence est 14 299 647,94 €. | Respecter le périmètre factures et avoirs et traiter un agrégat NULL comme un résultat à expliquer. |
| C03 · Marge d’EBITDA | Sans ontologie, l’agent atteint sa limite d’étapes. Avec ontologie, il annonce 100,86 % et son SQL exclut les comptes 60, 61 et 62 du numérateur. La référence est 9,40 %. | Vérifier les clauses d’inclusion dans le SQL. Le test isolé avait réussi, et la campagne a révélé que la bonne formule n’était pas stable. |
| C04 · Amortissements | Avec ontologie, PostgreSQL retourne bien 3 310 589,37 €. La réponse contient la trace SQL mais aucun texte de synthèse. Sans ontologie, le montant est formulé correctement. | Contrôler la réponse finale après une exécution réussie et fournir une synthèse ou un état explicite. |
| X03 · Rapprochement ERP–comptabilité | Avec ontologie, les montants et l’écart de 0 € sont justes, mais la phrase « Non, les chiffres sont identiques » se contredit. Le contrôle numérique passe. | Vérifier que la conclusion textuelle correspond au signe et à la valeur de l’écart. |
| P12 · Commission individuelle | Sans ontologie, l’outil bloque une recherche en paie. La réponse finale ne formule aucun refus. Avec ontologie, l’agent refuse explicitement sans appeler les outils. | Rendre le refus visible dès la demande de rémunération individuelle. Un blocage technique seul laisse l’utilisateur sans explication. |

X07 reste en erreur au niveau de l’agent dans le lot avec ontologie. Le fichier de campagne conserve le type `ExceptionGroup`. La cause interne de ce cas reste à isoler.

## Vérification après amélioration

La [campagne finale sur le Z4](results/quality_benchmark_z4.json) a exécuté les 45 questions sur le commit `641c284`, avec l’export et les règles déjà approuvés. Pour les mesures prises en charge, l’agent construit une requête à partir du calcul métier et de la période demandée. Le MCP conserve sa validation de lecture seule et son journal. La réponse est rendue à partir des lignes reçues et, pour les rapprochements, la conclusion est calculée avec le même écart. Une valeur SQL absente reste une absence. Qwen répond aux demandes qui ne relèvent pas des calculs pris en charge. Aucun attendu du jeu de test n’est transmis à l’agent.

| Contrôle | Résultat |
|---|---:|
| Questions numériques et références exécutées | 32/32 questions, 37/37 jeux de lignes conformes |
| Comportements attendus, revue assistée par IA | 13/13, aucune requête SQL exécutée |
| Erreurs au niveau de l’agent | 0 |
| Variantes de formulation et de période comparées à un SQL indépendant | 2/2 |
| Tests CPU | 74 réussis, 5 ignorés |

Le jeu connu a guidé les améliorations. Le score 45/45 décrit cette campagne, avec des verdicts assistés par IA pour les clarifications, les cas hors périmètre et les refus. Les variantes évaluées portent sur le CA facturé d’avril et l’EBITDA de février. Les questions de réserve du formateur restent un test distinct de généralisation. Les calculs contrôlés couvrent les formes reconnues. Si une formule ou le schéma évolue, revoir ensemble la définition approuvée, le calcul dans `metrics.py` et ses tests.

La comparaison appariée de la section précédente isole l’ontologie dans la version initiale. La campagne finale cumule un meilleur cadrage, des calculs contrôlés et une restitution à partir des résultats. Le score final mesure cet ensemble de changements.

## Obligations restant à terminer

- Relire les réponses avec le formateur et valider les verdicts sémantiques.
- Réaliser la démonstration avec la réserve du formateur.
- Préparer le dépôt privé de soumission `text2sql-calorvia`, ses tags et l'accès du formateur selon ses coordonnées effectivement fournies.

Le travail de code et de test de cette préparation est assisté par IA. La compétence indépendante de Mi reste évaluée séparément.

## Point de reprise 2

Les sauvegardes JSON atomiques et PostgreSQL interviennent après chaque question. Un verrou interprocessus exclut deux traitements Task 2 simultanés ; il ne connaît pas la charge du RAG. Les versions, le modèle, les données et les réglages sont conservés pour la reprise. Les métriques numériques sont des candidats à réviser, pas des scores sémantiques validés. Les campagnes complètes et leurs sauvegardes sont disponibles sur le Z4.
