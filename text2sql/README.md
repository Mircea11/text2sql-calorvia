# Calorvia — Text-to-SQL, checkpoint 1

**État : implémentation en cours, pas de rendu final.** Le brief original a été lu intégralement. Ce dossier est développé dans le dépôt RAG sans déplacer ni modifier ses modules, son environnement ou ses modèles.

## Résultats conservés

- 51 tables cataloguées : ERP 23, comptabilité 14, paie 14.
- Copies CPU de vérification : 139 308 / 101 045 / 217 612 lignes. Ces copies DuckDB ne remplacent pas les moteurs exigés.
- 44 questions de développement, dont 36 requêtes de référence vérifiées sur les scripts officiels. Aucun accès au jeu de réserve du formateur.
- 44 tests réussis ; 4 tests de privilèges natifs non exécutés ici.
- Échange MCP stdio réel et client officiel OpenAI testés sans modèle ni base distante.
- Les fichiers RAG existants sont conservés à l'identique.

## Carte des fichiers

| Fichier | But et relations | Résultat / vérification |
|---|---|---|
| `config.py` | Lit les `.env` existants ; partage les endpoints locaux | Pas de chargement GPU ; URL distante refusée |
| `catalog.py`, `ontology/catalog.json` | DDL officiels → tables, colonnes, PK/FK, commentaires | 23 + 14 + 14 tables vérifiées |
| `validation.py` | SQL du modèle → SELECT contrôlé et borné | Écritures, fonctions dangereuses, noms inconnus et données personnelles testés |
| `sources.py` | Outils MCP → connexions `agent_ro` → rollback | Code prêt ; pilotes/moteurs réels à tester sur la machine |
| `journal.py`, `journal.sql` | Accès sources → journal PostgreSQL existant | DSN ou transport Docker Calorvia ; essai natif en attente |
| `mcp_server.py` | Expose les six outils demandés, via stdio | Découverte et validation MCP testées |
| `agent.py` | LangGraph → outils MCP → réponse et preuves SQL | Boucle testée avec modèle simulé ; LLM réel en attente |
| `api.py` | Client OpenAI → agent ; SSE après calcul | Authentification, client SDK et SSE testés ; adaptateur lexical CPU à compléter/tester |
| `ontology.py`, `ontology/business.yaml` | Définitions métier → contexte de l'agent | Brouillon révisé par IA ; pas de certification humaine revendiquée |
| `auto_ontology.py`, `ontology/native_draft.yaml` | Import/compilation/export NVIDIA local | Brouillon natif prêt ; génération NVIDIA réelle non exécutée |
| `runtime.py` | Prépare des conteneurs CPU NVIDIA, modèles partagés | Configuration écrite en code ; démarrage Docker à vérifier |
| `offline.py` | Scripts officiels → copies CPU hors Git | 457 965 lignes chargées ; calculs de référence vérifiés |
| `evaluation.py`, `evaluation/questions.json` | Questions → références ; futur agent → mesures | 44 questions ; résultats CPU dans `results/offline_references.json` |
| `cli.py` | Commandes de préparation et d'exécution | Audit des dépendances et preflight exécutés |
| `tests/` | Contrats SQL, MCP, agent, API et privilèges | 44 passed / 4 skipped au checkpoint 1 |
| `CHECKPOINT.json` | État, fichiers, prochaines actions et limites | À lire avant toute reprise |

## Reprise

1. Lire `CHECKPOINT.json`, puis ce README. Ne pas recommencer l'implémentation.
2. Compléter et tester la génération NVIDIA, la preuve de provenance et les liens entre sources.
3. Compléter les métriques d'évaluation, la documentation d'installation, le rapport et la démonstration.
4. Refaire les contrôles locaux après les changements ; sauvegarder un nouveau checkpoint.
5. Demander une seule intervention groupée pour les accès/services de la machine qui restent indispensables.

## Commandes actuelles

Depuis la racine du dépôt, avec l'interpréteur de l'environnement existant :

```bash
python -m text2sql.cli dependencies
python -m pytest text2sql/tests -q
python -m text2sql.cli preflight
```

Ne pas exécuter `uv sync` pour cette préparation : les ajouts sont audités sans modifier les versions déjà installées. Ne lancer aucun nouveau modèle GPU.

Les sources officielles sont attendues dans `data/text2sql/sources_calorvia/`. Le port ERP réel du Compose fourni est **14330**, contrairement au port 1433 indiqué dans certaines parties du guide.

## Limites encore bloquantes

Ce workspace n'a ni Docker, ni les bases restaurées, ni les serveurs de modèles de la machine du cours. Il ne permet donc pas de prouver les ACL natives, de générer réellement l'ontologie NVIDIA, de mesurer la précision de l'agent ou de réaliser la démonstration finale. Aucun résultat de ces étapes n'est inventé.

Le brief demande un dépôt privé de soumission `text2sql-calorvia`, des tags par étape, une ontologie générée/certifiée, une comparaison avec/sans ontologie, un `RAPPORT.md` analysant cinq échecs et une démonstration de dix minutes. Ces obligations restent sur la checklist du rendu.

Les vérifications du checkpoint sont des réalisations assistées par IA ; elles ne constituent pas une preuve de maîtrise indépendante de Mi.
