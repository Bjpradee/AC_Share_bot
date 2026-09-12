import motor.motor_asyncio
from bson.objectid import ObjectId
from config import MONGO_URI, DB_NAME

class Database:
    def __init__(self, uri, database_name):
        # Added tls parameters to fix SSL handshake failure on GitHub Actions
        self._client = motor.motor_asyncio.AsyncIOMotorClient(
            uri, 
            tls=True, 
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=5000
        )
        self._db = self._client[database_name]
        self.col = self._db.file_store

    async def save_file(self, file_id, file_name, file_size):
        file_data = {
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size
        }
        result = await self.col.insert_one(file_data)
        return str(result.inserted_id)

    async def get_file(self, id):
        try:
            object_id = ObjectId(id)
            return await self.col.find_one({"_id": object_id})
        except Exception as e:
            print(f"Error fetching file: {e}")
            return None

db = Database(MONGO_URI, DB_NAME)
