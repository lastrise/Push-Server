from string import hexdigits
from random import choice
import aiohttp

from type.credentials import GoogleCredentials, FirebaseCredentials
from type.settings import FirebaseSettings
from dataclasses import dataclass
from typing import Optional


@dataclass()
class Installation:
    token: str
    iid: str


class Firebase:
    @staticmethod
    async def _getInstallation(settings: FirebaseSettings) -> Optional[Installation]:
        url = f"https://firebaseinstallations.googleapis.com/v1/projects/{settings.appName}/installations"
        headers = {"Content-Type": "application/json", "x-goog-api-key": settings.publicKey}
        data = {"fid": "dIsVQ2QVRT-TW7L6VfeAMh",
                "appId": settings.appId,
                "authVersion": "FIS_v2",
                "sdkVersion": "a:16.3.3"}

        async with aiohttp.ClientSession() as session:
            r = await session.post(url, headers=headers, json=data)
            if r.status != 200:
                return

            info = await r.json()
            return Installation(token=info["authToken"]["token"], iid=info["fid"])

    @staticmethod
    async def getCredentials(googleCr: GoogleCredentials, settings: FirebaseSettings) -> Optional[FirebaseCredentials]:
        installation = await Firebase._getInstallation(settings)
        url = "https://android.clients.google.com/c2dm/register3"
        headers = {"Authorization": f"AidLogin {googleCr.androidId}:{googleCr.securityToken}"}
        sender = settings.appId.split(":")[1]
        data = {"X-subtype": sender,
                "sender": sender,
                "X-appid": installation.iid,
                "X-Goog-Firebase-Installations-Auth": installation.token,
                "app": settings.appGroup,
                "device": googleCr.androidId}

        async with aiohttp.ClientSession() as session:
            r = await session.post(url=url, headers=headers, data=data)
            if r.status != 200:
                return

            pushToken = (await r.text()).replace("token=", "")
            deviceId = ''.join([choice(hexdigits) for _ in range(32)]).lower()
            return FirebaseCredentials(pushToken=pushToken, deviceId=deviceId)


testSettings = FirebaseSettings(publicKey="AIzaSyAOaoKaLhW98vLuaCuBqFh8qtLnh5c51z0",
                                appName="mcdonalds-70126",
                                appId="1:654771087992:android:79237bff987a6465",
                                appGroup="com.apegroup.mcdonaldrussia")
