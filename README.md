# Push-Server
Mock Android device with checkin and registering it in any application, after that we can listen this device for push-notifications. [GCM-REVERSE]

Создание Андройд-устройства и его регистрация в любом приложении, после этого можно прослушивать устройство на наличие пуш-уведомлений.

## Возможное применение
Может быть такое, что вам нужно будет автоматизировать какое-либо действие в приложении, связанное с пуш-уведомлениями.
Самый простой пример - создание виртуальной карты Тинькофф. При запросе на создание виртуальной карты требуется ввести код из СМС/Пуш-уведомления.
С помощью этой программы можно будет избавиться от ввода вручную... 

1. Делаем запрос на ожидание пуш-уведомления.
2. Дожидаемся сообщение.
3. Парсим оттуда код и отправляем запрос с ним.
4. Получаем виртуальную карту.

## Instructions

Uses mongodb with motor.

1. Clone this repository and install the dependencies: `pip install -r requirements.txt`
2. Make sure mongodb is running on the default port.
3. Run the application: `python app.py`
4. To create an Android device, you have to send an HTTP POST request to `http://localhost:5000/createDevice`.  
   All the necessary keys can be acquired by intercepting your app's initial request to `https://firebaseinstallations.googleapis.com/v1/projects/${appName}/installations`
   - `publicKey`: Value of the `x-goog-api-key` HTTP request header key
   - `appName`: Firebase app name, part of the query parameter (after `/projects/`) 
   - `appId`: Part of the request body
   - `appGroup`: Package name of the Android app, also present in the `X-Android-Package` HTTP request header
   
   ```shellSession
   curl -X POST -H 'content-type: application/json' 'http://localhost:5000/createDevice' --data @- <<EOF
   {
     "publicKey": "AIzaSyAOaoKaLhW98vLuaCuBqFh8qtLnh5c51z0",
     "appName": "mcdonalds-70126",
     "appId": "1:654771087992:android:79237bff987a6465",
     "appGroup": "com.apegroup.mcdonaldrussia"
   }
   EOF
   ```

5. The server responds with something like this:

   ```yaml
   {
       "androidId": "3887232111648592054",               # Used later to listen to the device
       "securityToken": "7868892933757783250",           # Used later to listen to the device
       "pushToken": "fYNtErlHZOVrPqGa3jEsze:APA91b...",  # You will need to register this token with the API of your app
       "deviceId": "cf8cdf0b9e9e03890ba5a7cb9d2c2134",   # Might be required when interacting with your app
       "uuid": "e88dfd2f-310b-487b-999e-d5a9579b4fc3"    # Unique database identifier
   }
   ```
6. Now, the device is ready to listen for push notifications. Make sure to register the `pushToken` with your app's API.
   To listen for new push notifications, send an HTTP POST request to `http://localhost:5000/getPushMessage`:
   
   ```shellSession
   curl -X POST -H 'content-type: application/json' 'http://localhost:5000/getPushMessage' --data @- <<EOF
   {
       "uuid": "3b51490d-45cc-44ee-913d-96fcb8bd6120",
       "application": "com.apegroup.mcdonaldrussia",
       "timeout": 180
   }
   EOF
   ```
   - `uuid`: Assigned after creating the device
   - `application`: `appGroup` of the application you want to receive push notifications for
   - `timeout`: Optional timeout in seconds; defaults to 180

7. Responds with the push notification if it arrives within the given timeout. Returns an error otherwise.
