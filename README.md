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

---

Fait avec ❤️ par Jules.
