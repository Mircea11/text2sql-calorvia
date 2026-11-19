# Démonstration de dix minutes — préparation

Cette procédure ne constitue pas une démonstration déjà réalisée. Les cinq questions finales appartiennent au formateur et ne sont pas connues ici.

## Avant le créneau

1. Vérifier les sources et les ACL natives ; conserver les sorties des tests.
2. Utiliser le serveur LLM existant, sans démarrer un second modèle.
3. Faire la génération/export NVIDIA puis arrêter uniquement ses conteneurs CPU s'ils ne servent plus. L'agent exploite ensuite l'export YAML local.
4. Démarrer l'API : `python -m text2sql.cli serve`.
5. Vérifier `/v1/models` avec la clé locale. Ne jamais afficher les `.env`.

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
