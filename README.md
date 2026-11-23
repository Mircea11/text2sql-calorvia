# Calorvia Text2SQL

Agent local qui transforme des questions métier en lectures SQL contrôlées sur GESPRO, comptabilité et paie. LangGraph orchestre Qwen. Le serveur MCP valide les requêtes et les exécute avec `agent_ro`. Le journal des accès utilise une base PostgreSQL distincte.

## Résultats à examiner

- [45 questions après amélioration](text2sql/results/quality_benchmark_z4.json) · 32 réponses numériques, 37 jeux de lignes vérifiés et 13 comportements attendus en revue assistée par IA.
- [Comparaison initiale avec et sans ontologie](text2sql/results/comparison.json) · 45 questions par lot et 13/32 contre 15/32 pour le contrôle numérique.
- [Rapport](text2sql/RAPPORT.md) · choix d’architecture, cinq échecs analysés, limites et approbation métier.
- [Export NVIDIA filtré](text2sql/ontology/auto_ontology_export.yaml) et [reçu](text2sql/ontology/generation_receipt.json) · 51 tables, huit définitions et cinq liens métier approuvés par Mi pour cet instantané.
- [Démonstration de dix minutes](text2sql/DEMO.md) · éléments à afficher et déroulé des cinq questions du formateur.

Les trois exports CSV dans [results](text2sql/results) contiennent les verdicts et durées par question. Les traces intégrales restent dans le journal et les fichiers locaux du Z4.

Le jeu connu a guidé les améliorations. Les questions de réserve restent l’épreuve de généralisation.

## Relancer sur un poste équipé

Utiliser Python 3.12 et les fichiers de sources fournis par le cours. Sur Z4, le Python déjà vérifié est celui de l’environnement partagé. Pour un nouveau poste, créer un environnement dédié.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r text2sql/requirements.in
cp text2sql/.env.example text2sql/.env
```

Configurer le fichier local avec le modèle compatible OpenAI, les ports des sources, le mot de passe `agent_ro`, une clé d’API Text2SQL et le DSN d’un journal PostgreSQL dédié. Le compte du journal doit pouvoir créer les tables dans cette base. Le DSN doit pointer vers une adresse locale. Sur Z4, les endpoints existants sont Qwen sur `127.0.0.1:8002/v1` et BGE-M3 sur `127.0.0.1:8000/v1`. Le port d’API du démonstrateur est configurable par `T2SQL_API_PORT`. Utiliser un port disponible.

### Sources et tests

Les scripts et le Compose des sources sont distribués par le cours. Préparer leur configuration locale et indiquer le chemin vers leur dossier `docker`.

```bash
.venv/bin/python text2sql/restore_postgres.py "/chemin/sources_calorvia/docker" compta
.venv/bin/python text2sql/restore_postgres.py "/chemin/sources_calorvia/docker" paie
.venv/bin/python text2sql/restore_erp.py "/chemin/sources_calorvia/docker"
.venv/bin/python -m text2sql init-journal
.venv/bin/python -m text2sql verify-sources
.venv/bin/python -m text2sql native-check
.venv/bin/python -m pytest text2sql/tests -q
T2SQL_LIVE=1 .venv/bin/python -m pytest text2sql/tests/test_live_permissions.py -q
```

### API et première question

```bash
.venv/bin/python -m text2sql serve
```

Exemple avec le port par défaut 9001. Fournir la clé locale dans la variable d’environnement `T2SQL_API_KEY` du terminal client et adapter le port configuré.

```bash
curl --fail http://127.0.0.1:9001/v1/chat/completions \
  -H "Authorization: Bearer ${T2SQL_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"calorvia-agent","messages":[{"role":"user","content":"Quelle est la marge d’EBITDA de mars 2026 ?"}]}'
```

La commande `.venv/bin/python -m text2sql ask --question "Quelle est la marge d’EBITDA de mars 2026 ?"` permet un contrôle local sans démarrer l’API. La [documentation détaillée](text2sql/README.md) contient la reprise des lots, la compilation et l’export NVIDIA. Pour une nouvelle compilation indépendante du dépôt RAG, renseigner explicitement `T2SQL_EMBED_URL` et `T2SQL_EMBED_MODEL`.

## Historique

L’historique de travail a été extrait du dépôt Calorvia en gardant les instantanés Text2SQL, les auteurs, les dates et les messages. Chaque commit extrait indique son identifiant source dans `Original-Calorvia-Commit`. Les empreintes dans les résultats restent celles mesurées lors des expériences sur le Z4. Les noms des tags correspondent aux étapes du brief.
