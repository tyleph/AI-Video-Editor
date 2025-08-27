import os
import json
import firebase_admin
from firebase_admin import credentials, storage, db

class FirebaseClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseClient, cls).__new__(cls)
            cls._instance._initialize_firebase()
        return cls._instance

    def _initialize_firebase(self):
        try:
            firebase_credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            if not firebase_credentials_json:
                raise ValueError("FIREBASE_CREDENTIALS_JSON environment variable not set.")

            cred = credentials.Certificate(json.loads(firebase_credentials_json))

            firebase_storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET")
            firebase_database_url = os.getenv("FIREBASE_DATABASE_URL")

            if not firebase_storage_bucket:
                raise ValueError("FIREBASE_STORAGE_BUCKET environment variable not set.")
            if not firebase_database_url:
                raise ValueError("FIREBASE_DATABASE_URL environment variable not set.")

            firebase_admin.initialize_app(cred, {
                'storageBucket': firebase_storage_bucket,
                'databaseURL': firebase_database_url
            })
            print("Firebase initialized successfully.")
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            raise

    def get_bucket(self):
        return storage.bucket()

    def db_ref(self):
        return db.reference()

# Singleton instance
firebase_client = FirebaseClient()
