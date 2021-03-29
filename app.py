import ssl
import varint

from random import getrandbits, choice
from string import digits
from typing import Optional, Tuple
from uuid import uuid4

from aiohttp import web, ClientSession
import asyncio

from checkin_pb2 import CheckinRequest, CheckinResponse
from type.credentials import GoogleCredentials
from firebase import Firebase
from mcs_pb2 import LoginRequest, LoginResponse, IqStanza, DataMessageStanza
from type.settings import FirebaseSettings
from pydantic.error_wrappers import ValidationError

from motor.motor_asyncio import AsyncIOMotorClient
from json.decoder import JSONDecodeError
import json

from time import time
from google.protobuf.json_format import MessageToDict

hexdigits = "ABCDEF0123456789"

client = AsyncIOMotorClient()
database = client["PUSH-SERVER"]


class Application:
    host = "localhost"
    port = 5000

    @staticmethod
    def _getCheckInData() -> bytes:
        req = CheckinRequest()
        req.imei = "109269993813709"
        req.androidId = 0
        req.checkin.build.fingerprint = "google/razor/flo:5.0.1/LRX22C/1602158:user/release-keys"
        req.checkin.build.hardware = "flo"
        req.checkin.build.brand = "google"
        req.checkin.build.radio = "FLO-04.04"
        req.checkin.build.clientId = "android-google"
        req.checkin.lastCheckinMs = 0
        req.locale = "en"
        req.loggingId = getrandbits(63)
        req.macAddress.append("".join(choice(hexdigits) for _ in range(12)))
        req.meid = "".join(choice(digits) for _ in range(14))
        req.accountCookie.append("")
        req.timeZone = "GMT"
        req.version = 3
        req.otaCert.append("--no-output--")
        req.esn = "".join(choice(hexdigits) for _ in range(8))
        req.macAddressType.append("wifi")
        req.fragment = 0
        req.userSerialNumber = 0

        return req.SerializeToString()

    @staticmethod
    async def _doCheckIn() -> Tuple[bool, Optional[GoogleCredentials]]:
        url = "https://android.clients.google.com/checkin"
        headers = {"Content-type": "application/x-protobuffer",
                   "Accept-Encoding": "gzip",
                   "User-Agent": "Android-Checkin/2.0 (vbox86p JLS36G); gzip"}
        data = Application._getCheckInData()

        async with ClientSession() as session:
            r = await session.post(url, headers=headers, data=data)
            if r.status != 200:
                return False, None

            resp = CheckinResponse()
            resp.ParseFromString(await r.read())

            return True, GoogleCredentials(androidId=resp.androidId, securityToken=resp.securityToken)

    @staticmethod
    async def createDevice(request: web.Request):

        """
        Example:
            publicKey: "AIzaSyAOaoKaLhW98vLuaCuBqFh8qtLnh5c51z0"
            appName: "mcdonalds-70126"
            appId: "1:654771087992:android:79237bff987a6465"
            appGroup: "com.apegroup.mcdonaldrussia"
        """

        if request.content_type != "application/json":
            return web.json_response({"error": "Content type is not 'application/json'"}, status=415)

        try:
            data = json.loads(await request.text())
        except JSONDecodeError:
            return web.json_response({"error": "Content type is not 'application/json'"}, status=415)

        try:
            settings = FirebaseSettings.parse_obj(data)
        except ValidationError:
            return web.json_response({"error": "Validation error"})

        isSuccessCheckin = False
        googleCredentials = None
        firebaseCredentials = None

        while not isSuccessCheckin:
            isSuccessCheckin, googleCredentials = await Application._doCheckIn()
            if not isSuccessCheckin:
                return web.json_response(data={"success": False})

            firebaseCredentials = await Firebase.getCredentials(googleCredentials, settings)
            if not firebaseCredentials:
                return web.json_response(data={"success": False})

            if "ERROR" in firebaseCredentials.pushToken:
                isSuccessCheckin = False
                await asyncio.sleep(1)

        uuid = str(uuid4())

        resp = {"androidId": googleCredentials.androidId,
                "securityToken": googleCredentials.securityToken,
                "pushToken": firebaseCredentials.pushToken,
                "deviceId": firebaseCredentials.deviceId,
                "uuid": uuid}

        await database.push.insert_one(resp)

        return web.json_response({"androidId": googleCredentials.androidId,
                                  "securityToken": googleCredentials.securityToken,
                                  "pushToken": firebaseCredentials.pushToken,
                                  "deviceId": firebaseCredentials.deviceId,
                                  "uuid": uuid})

    @staticmethod
    def _getLoginData(googleCredentials: GoogleCredentials) -> bytes:
        req = LoginRequest()
        req.adaptive_heartbeat = False
        req.auth_service = 2
        req.auth_token = googleCredentials.securityToken
        req.id = "android-11"
        req.domain = "mcs.android.com"
        req.device_id = "android-" + hex(int(googleCredentials.androidId))[2:]
        req.network_type = 1
        req.resource = googleCredentials.androidId
        req.user = googleCredentials.androidId
        req.use_rmq2 = True
        req.account_id = int(googleCredentials.androidId)
        req.received_persistent_id.append("")

        field = req.setting.add()
        field.name = "new_vc"
        field.value = "1"

        return req.SerializeToString()

    @staticmethod
    async def _readMessageLength(reader):

        async def readOneByte():
            c = await reader.read(1)
            if c == '':
                raise EOFError("Unexpected EOF while reading bytes")
            return ord(c)

        shift = 0
        result = 0
        while True:
            i = await readOneByte()
            result |= (i & 0x7f) << shift
            shift += 7
            if not (i & 0x80):
                break

        return result

    @staticmethod
    async def _readStream(reader, timeout: int = 1, length: int = 1) -> Optional[bytes]:
        try:
            return await asyncio.wait_for(
                reader.read(length), timeout=timeout
            )
        except asyncio.TimeoutError:
            return None

    @staticmethod
    async def _createPushConnection(cred: GoogleCredentials) -> Tuple[bool,
                                                                      Optional[asyncio.streams.StreamReader],
                                                                      Optional[asyncio.streams.StreamWriter]]:
        host = "alt3-mtalk.google.com"
        port = 5228

        try:
            streams: Tuple[asyncio.streams.StreamReader, asyncio.streams.StreamWriter] = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl.create_default_context()),
                timeout=3
            )
            reader, writer = streams
        except asyncio.TimeoutError:
            return False, None, None

        loginReq = Application._getLoginData(cred)

        writer.write(bytes([41]))
        writer.write(bytes([2]))
        writer.write(varint.encode(len(loginReq)))
        writer.write(loginReq)

        _ = await Application._readStream(reader, timeout=1, length=1)
        if not _:
            writer.close()
            return False, None, None

        prefix = await Application._readStream(reader, timeout=3, length=1)
        if not prefix:
            return False, None, None

        if prefix != b'\x03':
            writer.close()
            await writer.wait_closed()
            return False, None, None

        length = await Application._readMessageLength(reader)
        message = await Application._readStream(reader, timeout=3, length=length)
        if not message:
            return False, None, None

        resp = LoginResponse()
        resp.ParseFromString(message)

        return True, reader, writer

    @staticmethod
    async def _getMessage(reader: asyncio.streams.StreamReader,
                          writer: asyncio.streams.StreamWriter,
                          application: str,
                          timeout: int = 180) -> Optional[dict]:

        END_READING_DATA_MESSAGE = bytes.fromhex("070E10011A003A04080D120050036000")

        while timeout > 0:

            print(timeout, "Начал ждать новое сообщение")

            startEntry = time()

            prefix = await Application._readStream(reader, timeout=timeout, length=1)
            if not prefix:
                return None
            endEntry = time()
            interval = endEntry - startEntry
            timeout -= interval

            length = await Application._readMessageLength(reader)
            message = await Application._readStream(reader, timeout=1, length=length)
            if not message:
                return None

            print("Получил новое сообщение", message)

            if prefix == b'\x07':
                iqs = IqStanza()
                iqs.ParseFromString(message)

            elif prefix == b'\x08':
                dms = DataMessageStanza()
                dms.ParseFromString(message)
                dictMessage = MessageToDict(dms)
                writer.write(END_READING_DATA_MESSAGE)
                if "category" in dictMessage and dictMessage["category"] == application:
                    return dictMessage
            elif prefix == b'\x04':
                return None
            else:
                if not prefix:
                    return None

    @staticmethod
    async def getPushMessages(request: web.Request):

        """
        Example:
            uuid: "3b51490d-45cc-44ee-913d-96fcb8bd6120"
            application: "com.apegroup.mcdonaldrussia"
        """

        if request.content_type != "application/json":
            return web.json_response({"error": "Content type is not 'application/json'"}, status=415)

        try:
            data = json.loads(await request.text())
        except JSONDecodeError:
            return web.json_response({"error": "Content type is not 'application/json'"}, status=415)

        if "uuid" not in data or "application" not in data:
            return web.json_response({"error": "Validation error"}, status=415)

        document = await database.push.find_one({"uuid": data["uuid"]})
        if not document:
            return web.json_response({"error": "Unknown UUID"}, status=415)

        cred = GoogleCredentials(androidId=document["androidId"],
                                 securityToken=document["securityToken"])
        isSuccessConnection, reader, writer = await Application._createPushConnection(cred)
        if not isSuccessConnection:
            return web.json_response({"error": "Unsuccessful connection to MTalk"})

        timeout = 180
        if "timeout" in data:
            timeout = data["timeout"]

        message = await Application._getMessage(reader, writer, data["application"], timeout=timeout)
        writer.close()
        if not message:
            return web.json_response({"error": f"Did not get messages from {data['application']}"})

        return web.json_response({"message": message})


if __name__ == "__main__":
    app = web.Application()
    app.add_routes([web.post("/createDevice", Application.createDevice),
                    web.post("/getPushMessage", Application.getPushMessages)])
    web.run_app(host=Application.host, port=Application.port, app=app)
