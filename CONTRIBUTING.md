# Contribuer à Legal Git v1

Merci de votre intérêt — les contributions sont bienvenues.

## Préparer l'environnement

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cmake -S core -B core/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build core/build
```

## Avant chaque pull request

```bash
./core/build/core_tests          # 121 tests C++ — tous verts requis
.venv/bin/python -m pytest        # suite Python complète
```

La CI rejette toute PR dont un test échoue.

## Principes du projet (non négociables)

1. **Fidélité de la source** : le texte stocké est le texte source ;
   toute transformation documentée, jamais silencieuse.
2. **Immuabilité des versions** : aucune modification de
   `node_versions` — ORM, trigger, tests.
3. **Pas d'inférence d'identité** : la continuité d'un nœud vient de la
   preuve fournie par la source, jamais d'une ressemblance de contenu.
4. **Zéro interprétation juridique** : un diff est un relevé textuel ;
   l'ordre des versions est la chronologie de la source.
5. **Idempotence** : rejouer une ingestion ne crée rien.

## Conventions

- Python 3.12, type hints partout ; C++20, GoogleTest.
- Une PR = un sujet ; décrire le comportement observé sur des données
  réelles dans le message de commit.
- Ajouter un test qui échoue avant le correctif et passe après.

## Signalement

Ouvrez une issue avec : version du moteur, SGBD, extrait minimal
reproductible, comportement attendu. Les problèmes de sécurité se
réalisent en privé via https://app.hypetf.com.
