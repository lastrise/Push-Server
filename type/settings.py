from pydantic import BaseModel, Field


class FirebaseSettings(BaseModel):
    publicKey: str = Field()
    appName: str = Field()
    appId: str = Field()
    appGroup: str = Field()
