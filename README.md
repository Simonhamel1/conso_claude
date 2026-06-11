# Claude Usage Widget

Un petit widget de bureau (Windows) qui affiche en temps réel ta consommation de ton compte Claude : limite de session (5h) et limite hebdomadaire (7j), avec barres de progression et temps avant réinitialisation.

Léger, sans navigateur, conçu pour rester sous les 50 Mo de RAM.

## Aperçu

Le widget affiche :
- **Session (5h)** : pourcentage d'utilisation + temps avant réinitialisation
- **Semaine (7j)** : pourcentage d'utilisation + temps avant réinitialisation
- **Dernière actualisation** : heure du dernier rafraîchissement
- **Mémoire** : consommation RAM du widget (alerte si > 50 Mo)

Les barres et les pourcentages changent de couleur selon le niveau :
- 🟢 Vert : < 50 %
- 🔵 Bleu : 50–80 %
- 🔴 Rouge : ≥ 80 %

La fenêtre est sans bordure, toujours au premier plan, et déplaçable en glissant la barre de titre.

## Prérequis

- Python 3.8 ou plus
- Windows (testé sous Windows 10/11)

## Installation

1. Clone ou télécharge ce dossier dans `D:\conso_claude_widget` (ou ailleurs).

2. Installe les dépendances :

   ```bash
   pip install requests psutil
   ```

## Configuration

Ouvre `widget.py` et renseigne deux choses en haut du fichier :

```python
SESSION_KEY = "COLLE_TON_SESSION_KEY_ICI"
USAGE_URL = "https://claude.ai/api/organizations/TON_ORG_ID/usage"
```

### Récupérer ton sessionKey

Le `sessionKey` est le cookie de session de ton compte Claude. Il est nécessaire pour que le script puisse lire tes données d'usage.

1. Va sur claude.ai en étant connecté.
2. Appuie sur **F12** pour ouvrir les outils développeur.
3. Onglet **Application** (Chrome/Edge) ou **Stockage** (Firefox).
4. Dans la colonne de gauche : **Cookies** → `https://claude.ai`.
5. Trouve la ligne `sessionKey` et copie sa valeur (commence par `sk-ant-sid01-...`).
6. Colle-la dans `SESSION_KEY`.

> ⚠️ Le `sessionKey` est l'équivalent d'un mot de passe. Ne le partage avec personne et ne le commite jamais dans un dépôt public. Pour plus de sécurité, utilise une variable d'environnement plutôt qu'une valeur en dur.

Le cookie expire régulièrement : quand le widget affiche « ⚠ Erreur – vérifie ton sessionKey », il faut le récupérer à nouveau.

### Trouver ton ORG_ID

L'org ID est dans l'URL de l'API d'usage. Sur claude.ai connecté, ouvre l'onglet **Network** des outils développeur, cherche une requête vers `/api/organizations/.../usage` : l'identifiant entre `organizations/` et `/usage` est ton org ID.

## Utilisation

Lancement direct :

```bash
python widget.py
```

### Lancer avec la commande `conso`

Pour lancer le widget depuis n'importe où en tapant simplement `conso` :

**Option A — Fichier .bat (cmd / PowerShell)**

Crée `conso.bat` dans `D:\conso_claude_widget` :

```bat
@echo off
python "D:\conso_claude_widget\widget.py" %*
```

Puis ajoute `D:\conso_claude_widget` à ta variable d'environnement `Path` (Paramètres → Variables d'environnement → Path → Modifier → Nouveau). Rouvre ton terminal et tape `conso`.

**Option B — Fonction PowerShell**

```powershell
notepad $PROFILE
```

Ajoute :

```powershell
function conso { python "D:\conso_claude_widget\widget.py" $args }
```

Recharge avec `. $PROFILE`, puis tape `conso`.

## Paramètres

En haut de `widget.py` :

| Variable       | Description                                | Défaut  |
|----------------|--------------------------------------------|---------|
| `SESSION_KEY`  | Ton cookie de session Claude               | —       |
| `USAGE_URL`    | URL de l'API d'usage (avec ton org ID)     | —       |
| `REFRESH_MS`   | Intervalle d'actualisation (millisecondes) | 60000   |
| `MEM_LIMIT_MB` | Seuil d'alerte mémoire (Mo)                | 50      |

## Comment ça marche

Le widget interroge l'API d'usage de Claude via une simple requête HTTP (`requests`), en envoyant ton `sessionKey` comme cookie. La requête tourne dans un thread séparé pour ne pas geler l'interface. Un ramasse-miettes (`gc.collect()`) est appelé périodiquement pour garder la consommation mémoire basse.

## Dépannage

- **« ⚠ Erreur – vérifie ton sessionKey »** : ton cookie a expiré, récupère-le à nouveau.
- **`conso` non reconnu** : ferme et rouvre ton terminal après avoir modifié le PATH.
- **Mémoire qui dépasse 50 Mo** : la valeur est indicative ; Python ne peut pas plafonner strictement sa propre RAM, le widget alerte seulement.

## Avertissement

Projet personnel, non affilié à Anthropic. Il s'appuie sur une API interne non documentée de claude.ai qui peut changer ou cesser de fonctionner à tout moment.
