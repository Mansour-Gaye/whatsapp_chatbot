# Chatbox Assistant IA Ultra-Moderne

Ce projet fournit le code source pour une interface de chatbox web complète, conçue pour être facilement intégrée à n'importe quel site web. Le backend est construit avec Flask et le frontend est en JavaScript pur.

## Structure du Projet

-   `backend/app.py`: Le serveur principal Flask qui gère la logique du chat.
-   `backend/static/index.html`: La structure HTML de la chatbox.
-   `backend/static/css/styles.css`: Les styles pour la chatbox.
-   `backend/static/js/chatbot.js`: La logique frontend de la chatbox.
-   `requirements.txt`: Les dépendances Python pour le backend.

## Fonctionnalités

-   **Design Moderne** : Interface épurée, responsive et mobile-first.
-   **Haute Personnalisation** : Modifiez les couleurs, textes, avatars, et la position via JavaScript ou les paramètres d'URL.
-   **Composants Riches** : Support pour les réponses rapides et les cartes interactives.
-   **UX Avancée** : Indicateur de frappe, horodatage, confirmations de lecture.
-   **Persistance** : L'historique de la conversation est sauvegardé dans le `localStorage` du navigateur.
-   **Intégration Facile** : Intégrez-la via une `iframe` et configurez-la de manière flexible.

## Intégration

La méthode d'intégration recommandée est d'utiliser une `iframe` dans votre page web. Le serveur Flask sert la page de la chatbox à la route `/chatbot`.

**Exemple d'intégration dans votre page :**

```html
<!-- Placez cet élément où vous voulez sur votre page -->
<div style="position: fixed; bottom: 20px; right: 20px; width: 400px; height: 600px; z-index: 1000;">
    <iframe src="http://localhost:5000/chatbot"
            style="width: 100%; height: 100%; border: none;"
            title="Chatbot Assistant">
    </iframe>
</div>
```
*Note: Assurez-vous que l'URL (`src`) de l'iframe pointe vers l'adresse où votre serveur Flask est exécuté.*

## Configuration

Vous pouvez configurer la chatbox de deux manières :

### 1. Via l'objet `window.chatboxConfig` (Recommandé)

Dans votre page parente (celle qui contient l'iframe), définissez un objet global `window.chatboxConfig`. La chatbox dans l'iframe lira cette configuration. C'est la méthode la plus puissante et la plus flexible.

**Exemple Complet :**
```html
<script>
    window.chatboxConfig = {
        position: 'bottom-left', // 'bottom-right' ou 'bottom-left'
        theme: {
            primary: '#ff5733',
            userMessageBg: '#ff5733',
        },
        header: {
            title: 'Support Technique',
            botAvatar: '/static/img/avatar.png' // Chemin relatif au serveur Flask
        },
        welcomeMessage: 'Bonjour, je suis votre assistant technique. Comment puis-je aider ?',
        initialQuickReplies: ['Ouvrir un ticket', 'Documentation', 'Statut du service']
    };
</script>

<!-- L'iframe de la chatbox vient ensuite -->
<iframe src="http://localhost:5000/chatbot" ... ></iframe>
```

### 2. Via les Paramètres d'URL

Pour des ajustements rapides, vous pouvez passer des options de configuration directement dans l'URL de l'iframe. Ces paramètres surchargeront ceux définis dans `window.chatboxConfig`.

| Paramètre      | Description                                                               | Exemple                                      |
|----------------|---------------------------------------------------------------------------|----------------------------------------------|
| `primaryColor` | Couleur d'accentuation principale (hexadécimal, sans le `#`).             | `primaryColor=ff5733`                        |
| `position`     | Position du lanceur et de la fenêtre. `bottom-right` ou `bottom-left`.    | `position=bottom-left`                       |
| `title`        | Titre affiché dans l'en-tête de la chatbox.                               | `title=Aide+en+Ligne`                        |
| `avatar`       | URL de l'avatar du bot. Doit être encodée.                                | `avatar=%2Fstatic%2Fimg%2Fbot-logo.png`       |
| `basePath`     | Chemin de base pour les images (utile pour les avatars relatifs).         | `basePath=%2Fstatic%2Fimg%2F`                 |

**Exemple complet d'URL :**
`http://localhost:5000/chatbot?primaryColor=1a73e8&title=Assistant+de+Ventes&avatar=%2Fstatic%2Fimg%2Fcabine-pro.jpeg`

---

Fait avec ❤️ par Jules.

save : 
system_prompt = """# 
Tu es un assistant virtuel représentant **Translab International**, spécialisé dans la traduction, l’interprétation et la localisation. 
Ton rôle est de répondre aux utilisateurs de manière professionnelle, chaleureuse et concise (80% du temps en 1 à 3 phrases).

Contexte : {context}  
Historique : {history}  
Question de l’utilisateur : {question}  
Images disponibles : {available_images}  

### Instructions :
1. **Toujours être concis** : réponses courtes (1–3 phrases) sauf si une explication détaillée est nécessaire.  
2. **Images** : insérer une image pertinente (dans {available_images}) au moins tous les 5 messages. (ne salut pas l'utilisateur avec une image). #
3. **Services** : si la question concerne nos services, répondre clairement (ex: traduction certifiée, interprétation simultanée, localisation).  
4. **Devis** : si l’utilisateur demande un devis ou des prix → toujours l’orienter vers **contact@translab-international.com**.  
5. **Coordonnées** : si l’utilisateur demande "comment vous contacter" → fournir Tel, WhatsApp et Email.  
6. **Ton** : professionnel, chaleureux, avec emojis si pertinent (ex: 🙂, 🌍, 📞).  
7. **Toujours basé sur le contexte** : utiliser {context} pour fournir des réponses fiables et pertinentes.

### Exemples

**1️⃣ Questions à réponse courte**  
Q : "Bonjour, qui êtes-vous ?"  
R : Bonjour 🙂 Nous sommes **Translab International**, experts en traduction et interprétation à Dakar.  

Q : "Travaillez-vous uniquement au Sénégal ?"  
R : Non 🌍 Nous accompagnons aussi des clients internationaux.  

Q : "Faites-vous des traductions certifiées ?"  
R : ✅ Oui, pour contrats, diplômes et documents officiels.  

**2️⃣ Question à réponse avec image**  
Q : "Quels services proposez-vous ?"  
R :  
[image: service1.jpeg]  
### 🌟 Nos Services  
- Traduction certifiée  
- Interprétation simultanée, consécutive et distancielle  
- Localisation de contenus  

**3️⃣ Question à réponse longue/détaillée**  
Q : "Pouvez-vous expliquer votre service d’interprétation simultanée ?"  
R : L’interprétation simultanée consiste à traduire oralement en temps réel lors de conférences ou réunions internationales. Nos interprètes expérimentés utilisent des cabines et des équipements professionnels pour garantir une qualité optimale. Nous offrons également la possibilité de sessions distancielles via Zoom ou Teams. Ce service permet aux participants de comprendre immédiatement les interventions, même dans plusieurs langues, et assure une communication fluide et efficace lors d’événements multilingues. """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])
        logger.info("Template de prompt créé")

        if not llm:
            logger.warning("LLM non disponible, la chaîne RAG ne peut pas être créée.")
            return None

        # Créer la chaîne RAG
        rag_chain = RunnableMap({
            "context": lambda x: "\n\n".join([doc.page_content for doc in retriever.invoke(x["question"])]),
            "question": lambda x: x["question"],
            "history": lambda x: x.get("history", []),
            "available_images": lambda x: ", ".join(AVAILABLE_IMAGES) if AVAILABLE_IMAGES else "Aucune"
        }) | prompt | llm
        
        logger.info("Chaîne RAG créée avec succès")
        return rag_chain
        
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la chaîne RAG: {str(e)}")
        return None