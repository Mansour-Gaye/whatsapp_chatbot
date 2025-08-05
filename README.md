# Chatbox Assistant IA Ultra-Moderne


Ce projet contient le code source pour une interface de chatbox web complète, minimaliste, et hautement personnalisable. Elle est conçue pour être facilement intégrée à n'importe quel site web via une `iframe`.

Le projet est structuré comme suit :
- `index.html`: Une page d'exemple montrant comment héberger la chatbox.
- `chatbot.html`: Le composant de chatbox autonome.
- `style.css`: Les styles pour la chatbox.
- `script.js`: La logique de la chatbox.


## Fonctionnalités

- **Design Moderne** : Interface épurée, responsive et mobile-first.
- **Thème Clair/Sombre Automatique** : S'adapte aux préférences du système.
- **Haute Personnalisation** : Modifiez les couleurs, textes, avatars, position, et chemins d'accès aux images.
- **Composants Riches** : Support pour les réponses rapides et les cartes interactives.
- **UX Avancée** : Indicateur de frappe, horodatage, confirmations de lecture.
- **Persistance** : L'historique de la conversation est sauvegardé dans le `localStorage`.

## Intégration

L'intégration se fait en insérant une `iframe` dans votre page web. Vous pointez le `src` de l'iframe vers `chatbot.html` et vous passez la configuration via les paramètres d'URL.

**Exemple d'intégration dans votre page :**

```html
<div style="position: fixed; bottom: 0; right: 0; width: 400px; height: 600px; z-index: 1000;">
    <iframe src="/chemin/vers/votre/chatbot.html?primaryColor=5A3E8A&title=Support"
            style="width: 100%; height: 100%; border: none;"
            title="Chatbot Assistant">
    </iframe>
</div>
```

## Configuration via Paramètres d'URL

Personnalisez la chatbox en ajoutant des paramètres à l'URL de l'iframe.

| Paramètre        | Description                                                                    | Exemple                                        |
|------------------|--------------------------------------------------------------------------------|------------------------------------------------|
| `primaryColor`   | Couleur d'accentuation principale (hexadécimal, sans le `#`).                  | `primaryColor=ff5733`                          |
| `position`       | Position du lanceur et de la fenêtre. `bottom-right` ou `bottom-left`.         | `position=bottom-left`                         |
| `title`          | Titre affiché dans l'en-tête de la chatbox.                                    | `title=Aide en Ligne`                          |
| `avatar`         | URL de l'avatar du bot. Doit être encodée si elle contient des caractères spéciaux. | `avatar=https%3A%2F%2F...%2Flogo.png`           |
| `basePath`       | Chemin de base pour les images (avatar, cartes).                               | `basePath=%2Fstatic%2Fimg%2F`                   |

**Exemple complet :**
`chatbot.html?primaryColor=1a73e8&title=Assistant de Ventes&basePath=%2Fassets%2F`

Si vous utilisez `basePath`, vous pouvez ensuite définir un avatar avec un chemin relatif comme `avatar=bot-logo.png`.
=======
- **Thème Clair/Sombre Automatique** : S'adapte aux préférences du système d'exploitation de l'utilisateur.
- **Haute Personnalisation** : Modifiez les couleurs, textes, avatars, position et plus encore.
- **Composants Riches** : Support pour les réponses rapides, les cartes interactives.
- **UX Avancée** : Indicateur de frappe, horodatage, confirmations de lecture.
- **Persistance** : L'historique de la conversation est sauvegardé dans le `localStorage` du navigateur.
- **Intégration Facile** : Configurable via un objet JavaScript ou des paramètres d'URL.

## Intégration

Vous avez deux manières d'intégrer la chatbox à votre site.

### Méthode 1 : Inclusion Directe (Recommandé)

1.  Placez les fichiers `index.html`, `style.css`, et `script.js` sur votre serveur.
2.  Dans votre page web principale, vous pouvez charger la chatbox en utilisant une `iframe` pour une isolation parfaite :

    ```html
    <iframe src="/chemin/vers/votre/chatbox/index.html"
            style="position: fixed; bottom: 0; right: 0; border: none; width: 400px; height: 600px; z-index: 1000;"
            title="Chatbot Assistant">
    </iframe>
    ```
    *Note : L'iframe ci-dessus est un exemple simple. La chatbox gère elle-même sa position et sa visibilité via le bouton de lancement.*

    Pour une intégration plus directe, vous pouvez inclure le CSS et le JS, puis copier le contenu de la `<body>` de `index.html` dans votre page principale.

### Méthode 2 : Configuration via `iframe` et URL

Vous pouvez configurer la chatbox directement depuis l'URL de l'iframe.

```html
<iframe src="/chemin/vers/chatbox/index.html?primaryColor=ff5733&position=bottom-left&title=Support Client" ...></iframe>
```

## Configuration

La chatbox est conçue pour être flexible. Vous pouvez la configurer de deux manières.

### 1. Via l'objet `window.chatboxConfig` (Méthode recommandée)

Avant de charger le `script.js` de la chatbox (ou dans la page parente si vous utilisez une `iframe`), définissez un objet global `window.chatboxConfig`.

**Exemple Complet :**
Ajoutez ce script dans votre page HTML principale.

```html
<script>
    window.chatboxConfig = {
        position: 'bottom-left', // 'bottom-right' ou 'bottom-left'
        mode: 'floating',        // 'floating' ou 'fullscreen'
        theme: {
            primary: '#ff5733',
            userMessageBg: '#ff5733',
        },
        header: {
            title: 'Support Technique',
            botAvatar: '/chemin/vers/votre/logo.png'
        },
        welcomeMessage: 'Bonjour, je suis votre assistant technique. Comment puis-je aider ?',
        initialQuickReplies: ['Ouvrir un ticket', 'Documentation', 'Statut du service']
    };
</script>
<!-- Ensuite, chargez le script de la chatbox ou l'iframe -->
```

### 2. Via les Paramètres d'URL

Vous pouvez passer des options de configuration simples directement dans l'URL. C'est utile pour des modifications rapides ou pour l'intégration via `iframe`.

**Paramètres disponibles :**
- `primaryColor` : Couleur d'accentuation principale (en hexadécimal, sans le `#`).
- `position` : `bottom-right` ou `bottom-left`.
- `title` : Le titre affiché dans l'en-tête de la chatbox.

**Exemple :**
`https://votresite.com/chatbox/index.html?primaryColor=e040fb&position=bottom-left&title=FAQ`


---

Fait avec ❤️ par Jules.
