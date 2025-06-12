from typing import List, Optional
import os
import requests
from langchain_core.embeddings import Embeddings

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
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Génère les embeddings pour une liste de textes.
        
        Args:
            texts: Liste de textes à encoder
            
        Returns:
            Liste d'embeddings (vecteurs)
        """
        if not texts:
            return []
            
        # Préparer la requête
        payload = {
            "input": texts,
            "model": "jina-embeddings-v3",
            "task_type": "retrieval.passage"  # Optimisé pour les documents
        }
        
        # Envoyer la requête
        response = requests.post(self.api_url, headers=self.headers, json=payload)
        response.raise_for_status()
        
        # Extraire les embeddings
        result = response.json()
        return [item["embedding"] for item in result["data"]]
    
    def embed_query(self, text: str) -> List[float]:
        """Génère l'embedding pour une requête.
        
        Args:
            text: Texte à encoder
            
        Returns:
            Embedding (vecteur)
        """
        # Préparer la requête
        payload = {
            "input": [text],
            "model": "jina-embeddings-v3",
            "task_type": "retrieval.query"  # Optimisé pour les requêtes
        }
        
        # Envoyer la requête
        response = requests.post(self.api_url, headers=self.headers, json=payload)
        response.raise_for_status()
        
        # Extraire l'embedding
        result = response.json()
        return result["data"][0]["embedding"] 