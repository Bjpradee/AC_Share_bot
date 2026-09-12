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
        self.users_col = self._db.users
        self.settings_col = self._db.bot_settings

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
        await self.col.update_one(
            {"_id": custom_id},
            {"$set": file_data},
            upsert=True
        )
        return str(custom_id)

    async def get_file(self, id):
        try:
            numeric_id = int(id)
            file_data = await self.col.find_one({"_id": numeric_id})
            if file_data:
                return file_data
        except ValueError:
            pass
        return await self.col.find_one({"_id": id})

    async def add_user(self, user_id):
        is_exist = await self.users_col.find_one({"user_id": user_id})
        if not is_exist:
            await self.users_col.insert_one({"user_id": user_id})

    async def total_users_count(self):
        return await self.users_col.count_documents({})

    async def get_all_users(self):
        return self.users_col.find({})

    async def get_fsub_channels(self):
        data = await self.settings_col.find_one({"_id": "fsub_channels"})
        return data.get("channels", []) if data else []

    async def set_fsub_channels(self, channels_list):
        await self.settings_col.update_one(
            {"_id": "fsub_channels"},
            {"$set": {"channels": channels_list}},
            upsert=True
        )

db = Database(MONGO_URI, DB_NAME)
