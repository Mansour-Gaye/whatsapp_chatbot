from typing import List, Optional
import os
import requests
import logging
from langchain_core.embeddings import Embeddings

# Configuration du logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class JinaEmbeddings(Embeddings):
    """Classe pour gérer les embeddings via l'API Jina."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialise le client Jina.
        
        Args:
            api_key: Clé API Jina. Si non fournie, utilise JINA_API_KEY de l'environnement.
        """
        self.api_key = api_key or os.getenv("JINA_API_KEY")
        if not self.api_key:
            raise ValueError("JINA_API_KEY doit être fournie ou définie dans l'environnement")
        
        self.api_url = "https://api.jina.ai/v1/embeddings"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info("JinaEmbeddings initialisé avec succès")
    
    def _make_request(self, payload: dict) -> dict:
        """Fait une requête à l'API Jina avec gestion des erreurs.
        
        Args:
            payload: Données à envoyer à l'API
            
        Returns:
            Réponse de l'API au format JSON
        """
        try:
            logger.debug(f"Envoi de la requête à Jina API: {payload}")
            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la requête à l'API Jina: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Réponse de l'API: {e.response.text}")
            raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Génère les embeddings pour une liste de textes.
        
        Args:
            texts: Liste de textes à encoder
            
        Returns:
            Liste d'embeddings (vecteurs)
        """
        if not texts:
            return []
            
        try:
            # Préparer la requête avec le bon format
            payload = {
                "task": "retrieval.passage",
                "model": "jina-embeddings-v3",
                "input": texts
            }
            
            # Envoyer la requête
            result = self._make_request(payload)
            
            # Extraire les embeddings
            embeddings = [item["embedding"] for item in result["data"]]
            logger.info(f"Embeddings générés pour {len(texts)} documents")
            return embeddings
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération des embeddings pour les documents: {str(e)}")
            raise
    
    def embed_query(self, text: str) -> List[float]:
        """Génère l'embedding pour une requête.
        
        Args:
            text: Texte à encoder
            
        Returns:
            Embedding (vecteur)
        """
        try:
            # Préparer la requête avec le bon format
            payload = {
                "task": "retrieval.query",
                "model": "jina-embeddings-v3",
                "input": [text]
            }
            
            # Envoyer la requête
            result = self._make_request(payload)
            
            # Extraire l'embedding
            embedding = result["data"][0]["embedding"]
            logger.info("Embedding généré pour la requête")
            return embedding
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération de l'embedding pour la requête: {str(e)}")
            raise 