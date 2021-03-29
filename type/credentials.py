from pydantic import BaseModel, Field


class GoogleCredentials(BaseModel):
    androidId: str = Field()
    securityToken: str = Field()


class FirebaseCredentials(BaseModel):
    pushToken: str = Field()
    deviceId: str = Field()

