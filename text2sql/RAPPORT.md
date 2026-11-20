# Calorvia Text-to-SQL — rapport de préparation

**Statut : code et vérifications locales disponibles ; rendu natif incomplet.** Les résultats ci-dessous ne mesurent pas encore la précision d'un agent utilisant les serveurs du cours.

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
| Génération NVIDIA réelle | Non exécutée | Aucune ontologie humaine certifiée revendiquée |
| Agent réel avec / sans ontologie | Non exécuté | Aucun score de précision, validité SQL ou latence de modèle inventé |

## Corrections de définitions déjà vérifiées

| Définition initiale insuffisante | Observation | Définition corrigée |
|---|---|---|
| Somme des montants de factures | Les avoirs sont positifs dans l'ERP | Soustraire les lignes de type A ; CA net facturé de mars 2026 : 13 599 646,63 € |
| Classes 6 et 7 pour le résultat annuel, sans autre filtre | Le bénéfice affecté au compte 693000 annule le résultat | Exclure les affectations 69/79 ; résultat net 2025 : 5 412 000,00 € |
| EBITDA limité aux ventes 70 et charges 60–62 | L'exemple officiel comprend aussi les autres produits | Inclure les produits 7 hors 79 et charges 60–62 ; EBITDA mars : 1 278 366,78 €, marge sur CA 70 : 9,4 % |
| « Unités achetées » sans préciser les avoirs | 1 230 unités sur factures F, 960 nettes après avoirs | La question de développement précise « hors avoirs » ; aucune règle spécifique à un client n'est injectée |

Ces corrections sont des vérifications assistées par IA sur références. Elles ne constituent pas la certification humaine demandée par le brief.

## Confidentialité

Le démonstrateur ne dispose pas d'une identité RH vérifiée. Il refuse donc les identités de paie et les rémunérations/commissions individuelles, même par filtre ou sous-requête, et autorise les agrégats contrôlés. Pour les montants de rémunération, la validation ajoute HAVING COUNT(DISTINCT employee_id) >= 5 et refuse les sous-requêtes complexes. Cette borne réduit les révélations directes ; elle ne constitue pas une protection statistique contre des attaques adaptatives par différences. Cette décision entraîne un refus intentionnel de l'exemple individuel « commission de Joris Claes ». Ce refus est explicitement évalué comme une politique choisie, et non comme une réponse numérique correcte à l'exemple initial.

Les numéros nationaux, IBAN, adresses privées et autres champs sensibles sont refusés par la validation. Les privilèges natifs fournis doivent être testés séparément, notamment après désactivation du défaut de transaction read-only. L'absence d'écriture ne dépend pas uniquement d'un prompt.

## Comparaison d'expériences et analyse de cinq échecs

**En attente d'exécutions réelles.** Le jeu attendu reste à l'extérieur du contexte de l'agent. Le mode sans ontologie retire également les termes des fiches de tables pour éviter de contaminer la référence. Les contrôles numériques utilisent une tolérance de 0,01 ; ils ne suffisent pas à certifier le sens, la période, l'unité ni la qualité d'un refus. Une revue sémantique des réponses est donc encore nécessaire.

L'analyse finale doit sélectionner cinq questions réellement ratées et localiser l'échec : source/routage, définition métier, génération SQL, validation, exécution, rapprochement ou formulation. Aucun échec de modèle n'est inventé à partir des erreurs de préparation ci-dessus.

## Obligations restant à terminer

- Vérifier les 37 requêtes de référence sur les moteurs natifs. Les trois restaurations et les quatre tests d’ACL sont confirmés sur le Z4.
- Vérifier les endpoints partagés et la sortie structurée attendue par NVIDIA.
- Compiler réellement, exporter puis faire réviser/certifier les termes importants.
- Mesurer deux expériences complètes et comparables avec commit Git propre ; journaliser/exporter les résultats.
- Analyser les cinq échecs observés et réaliser la démonstration avec la réserve du formateur.
- Préparer le dépôt privé de soumission `text2sql-calorvia`, ses tags et l'accès du formateur selon ses coordonnées effectivement fournies.

Le travail de code et de test de cette préparation est assisté par IA. La compétence indépendante de Mi reste évaluée séparément.

## Point de reprise 2

Les sauvegardes JSON atomiques et PostgreSQL interviennent après chaque question. Un verrou interprocessus exclut deux traitements Task 2 simultanés ; il ne connaît pas la charge du RAG. Les versions, le modèle, les données et les réglages sont conservés pour la reprise. Les métriques numériques sont des candidats à réviser, pas des scores sémantiques validés. Les campagnes complètes restent à exécuter sur le Z4.
