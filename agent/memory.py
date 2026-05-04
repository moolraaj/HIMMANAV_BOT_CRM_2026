# agent/memory.py
from typing import Dict, List
import chromadb
from datetime import datetime

class AgentMemory:
    """Long-term memory for user preferences"""
    
    def __init__(self):
        self.client = chromadb.Client()
        self.collection = self.client.create_collection("user_preferences")
    
    def remember_preference(self, phone: str, preference: str, value: any):
        """Store user preference"""
        self.collection.upsert(
            ids=[f"{phone}_{datetime.now().timestamp()}"],
            documents=[f"{preference}: {value}"],
            metadatas=[{"phone": phone, "preference": preference}]
        )
    
    def recall_preferences(self, phone: str) -> Dict:
        """Retrieve user preferences"""
        results = self.collection.query(
            where={"phone": phone},
            n_results=10
        )
        # Parse and return preferences
        return self._parse_preferences(results)