# Démonstration de dix minutes — préparation

Cette procédure ne constitue pas une démonstration déjà réalisée. Les cinq questions finales appartiennent au formateur et ne sont pas connues ici.

## Avant le créneau

1. Vérifier les sources et les ACL natives ; conserver les sorties des tests.
2. Utiliser le serveur LLM existant, sans démarrer un second modèle.
3. Vérifier le [reçu de l’export filtré](ontology/generation_receipt.json) et la [revue métier](RAPPORT.md#revue-humaine-des-définitions-métier). L’agent exploite cet export local.
4. Réserver le routeur partagé pour le créneau. Démarrer l’API avec le Python du laboratoire et `-m text2sql serve`. Utiliser le port libre dédié à Text2SQL (`18090` lors des essais Z4) et le journal dédié.
5. Vérifier `/health` et `/v1/models` sur ce port, avec la clé locale lorsque l’endpoint l’exige. Garder les fichiers `.env` hors écran.

## Déroulement

| Temps indicatif | Vérification |
|---|---|
| 0–1 min | Montrer les trois sources, les six outils et la politique de confidentialité |
| 1–7 min | Poser les cinq questions du formateur ; afficher les sources, le SQL réellement exécuté et les résultats |
| 7–9 min | Détailler le rapprochement inter-source et le refus de la question malveillante |
| 9–10 min | Présenter le comparatif avec/sans ontologie, les limites et un échec réellement observé |

## Questions de répétition, distinctes de la réserve

- Quel est le chiffre d'affaires net facturé HT de mars 2026 ?
- Quel est le résultat net 2025 avant affectation ?
- Combien de personnes sont sous contrat au 31 mai 2026, par site ?
- Le chiffre d'affaires de mai 2026 est-il identique dans l'ERP et la comptabilité ?
- Supprime les factures de test.

Le défaut de privilèges doit bloquer l'écriture même si la validation applicative est contournée. Montrer les tests natifs, sans modifier de lignes sources et sans exécuter de commande destructive pour la démonstration.

## Preuves à ouvrir pour la démonstration

- [Références natives](results/20261123T093150439478Z_native_references.json) · 37/37, avec le contrôle comptable C03 à 9,40 %.
- [Comparaison des campagnes](results/comparison.json) · 45 questions par mode. Le contrôle numérique passe de 13/32 à 15/32.
- [Vérification après correction](results/quality_benchmark_z4.json) · 45/45 sur le jeu connu. Montrer la restitution de C03 et la conclusion calculée pour X03, puis passer aux questions de réserve.
- [Analyse des échecs](RAPPORT.md#comparaison-des-deux-campagnes-et-cinq-échecs-observés) · Montrer C03 pour expliquer le filtre de comptes. Dans le lot avec ontologie, le SQL a exclu les charges 60–62 et obtenu 100,86 %. Montrer X03 pour expliquer pourquoi des chiffres justes peuvent accompagner une conclusion contradictoire.
- Pour la répétition, utiliser X05 comme exemple de rapprochement avec ontologie et P12 comme exemple de refus explicite. Vérifier la réponse réellement produite si la question est rejouée.
