import motor.motor_asyncio
from config import MONGO_URI, DB_NAME

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(
            uri, 
            tls=True, 
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=5000
        )
        self._db = self._client[database_name]
        self.col = self._db.file_store
        self.counter_col = self._db.id_counter

    async def get_next_id(self):
        counter = await self.counter_col.find_one_and_update(
            {"_id": "file_id_counter"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=motor.motor_asyncio.ReturnDocument.AFTER
        )
        return counter["seq"]

    async def save_file(self, file_id, file_name, file_size, custom_id=None):
        if custom_id is None:
            custom_id = await self.get_next_id()
            
        file_data = {
            "_id": custom_id,
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size
        }
        # Upsert to avoid duplication if same ID exists
        await self.col.update_one(
            {"_id": custom_id},
            {"$set": file_data},
            upsert=True
        )
        return str(custom_id)

    async def get_file(self, id):
        try:
            # Try searching as integer first, then string if needed
            numeric_id = int(id)
            file_data = await self.col.find_one({"_id": numeric_id})
            if file_data:
                return file_data
        except ValueError:
            pass
            
        return await self.col.find_one({"_id": id})

db = Database(MONGO_URI, DB_NAME)
