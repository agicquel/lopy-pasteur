from network import WLAN
from network import LoRa
from microWebSrv import MicroWebSrv
from logger import Log
from led import Led
import machine
import network
import time
import config
import ujson
import pycom
from network import Server
import ubinascii
import socket

Log.i("LoPy launched")
Led.blink_red()
time.sleep(10)

############################ Configure ESP vars ############################
esp_subscribed = []
esp_messages = {}
esp_id_ip = {}
############################################################################


############################## Configure LoRa ##############################
lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868)
lopyMAC = ubinascii.hexlify(lora.mac()).upper().decode('utf-8')

messageReceived = False

socketLora = socket.socket(socket.AF_LORA, socket.SOCK_RAW)
socketLora.setsockopt(socket.SOL_LORA, socket.SO_DR, 5)
socketLora.setsockopt(socket.SOL_LORA, socket.SO_CONFIRMED, False)
socketLora.bind(config.LORA_FPORT)
socketLora.settimeout(60)

app_eui = ubinascii.unhexlify(config.LORA_APP_ID)
app_key = ubinascii.unhexlify(config.LORA_APP_KEY)

def _callback(message):
    Log.i("_callback")
    if(not messageReceived):
        return
    message = message.decode()
    Log.i("message decode = " + message)
    parsed = ujson.loads(message)
    for m in parsed:
        mId = str(m.get("espId"))
        mMes = str(m.get("message"))
        if mId and mMes :
            esp_messages[mId] = mMes

def _lora_callback(trigger):
    Log.i("_lora_callback")
    global messageReceived
    events = lora.events()
    if(events & LoRa.RX_PACKET_EVENT):
        messageReceived = True
        socketLora.setblocking(True)
        Log.i("LoRa.RX_PACKET_EVENT")
        Led.blink_yellow()
        data = socketLora.recv(256)
        socketLora.setblocking(True)
        _callback(data)
    #    if(events & LoRa.TX_PACKET_EVENT):
    #        Log.i("LoRa.TX_PACKET_EVENT")
    if(events & LoRa.TX_FAILED_EVENT):
        Log.i("LoRa.TX_FAILED_EVENT")
        _join()

lora.callback(trigger=(LoRa.RX_PACKET_EVENT | LoRa.TX_FAILED_EVENT), handler=_lora_callback)

def _join():
    if not lora.has_joined():
        Log.i("Connecting Lora...")
        Led.blink_yellow()
        lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0)
        while not lora.has_joined():
            time.sleep(2.5)
        Led.blink_green()
        Log.i("Connected")
        
def send(message):
    Log.i("Sending : " + message)
    global messageReceived
    Led.blink_purple()
    _join()
    messageReceived = False
    attemptCounter = 0

    while(not messageReceived and attemptCounter < 5):
        socketLora.send(message.encode())
        time.sleep(5)
        attemptCounter = attemptCounter + 1

    Led.blink_orange()
    Log.i("Message sent")
############################################################################


############################## Configure Wifi ##############################
wlan = WLAN(mode=WLAN.AP, ssid=config.WIFI_SSID, auth=(WLAN.WPA2, config.WIFI_PASS), channel=11, antenna=WLAN.INT_ANT)
wlan.ifconfig(id=1, config=(config.API_HOST, '255.255.255.0', '10.42.31.1', '8.8.8.8'))
############################################################################


######################### Configure FTP and Telnet #########################
server = network.Server()
server.deinit() # disable
############################################################################


########################## Configure microWebSrv ###########################
# DOC : https://github.com/jczic/MicroWebSrv

@MicroWebSrv.route('/subscribe', 'POST')
def handlerFuncPost(httpClient, httpResponse):
        global esp_subscribed
        global esp_messages
        global esp_id_ip
        params  = httpClient.GetRequestQueryParams()
        if "espid" in params:
            espid = params["espid"]
            Log.i("new sub espId : " + espid)
            if espid not in esp_subscribed:
                esp_subscribed.append(espid)
                esp_messages[espid] = espid
                esp_id_ip[espid] = httpClient.GetIPAddr()
            httpResponse.WriteResponseOk(
                headers=None,
                contentType="text/plain",
                contentCharset="UTF-8",
                content="Subscribed"
            )
        else:
            httpResponse.WriteResponseForbidden()

@MicroWebSrv.route('/subscribed/<espid>')
def handlerFuncSub(httpClient, httpResponse, routeArgs):
        global esp_subscribed
        espid = routeArgs['espid']
        if espid in esp_subscribed:
            httpResponse.WriteResponseOk()
        else:
            httpResponse.WriteResponseForbidden()

@MicroWebSrv.route('/message/<espid>')
def handlerFuncEdit(httpClient, httpResponse, routeArgs):
        global esp_subscribed
        global esp_messages
        espid = routeArgs['espid']
        if espid in esp_subscribed:
            httpResponse.WriteResponseOk(
                headers=None,
                contentType="text/plain",
                contentCharset="UTF-8",
                content=esp_messages.get(espid)
            )
        else:
            httpResponse.WriteResponseForbidden()

@MicroWebSrv.route('/messages')
def handlerFuncGet(httpClient, httpResponse):
        response = """\
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8" />
                <title>ESP MESSAGES</title>
            </head>
            <body>
                <h3>LoPy : {mac_address}</h3>
                <table border="1">
                <tr>
                    <th>ESP ID</th>
                    <th>Message</th>
                </tr>
            """.format(mac_address = lopyMAC)
        for espid, espmes in esp_messages.items():
            response += "<tr>\n<td>" + espid + "</td>"
            response += "\n<td>" + espmes + "</td>\n</tr>"
        response += """\
                        </tr>
                        <tr>
                    </table>
                    <br>
                    
                    <iframe id="iframe3"
                        title="iframe2"
                        width="600"
                        height="900"
                        src="http://10.42.31.3/">
                    </iframe>

                </body>
            </html>
            """
        httpResponse.WriteResponseOk(
            headers = None,
            contentType = "text/html",
            contentCharset = "UTF-8",
            content = response
        )

@MicroWebSrv.route('/')
def handlerFuncIndex(httpClient, httpResponse):
        response = """\
                <!DOCTYPE html>
                <html>
                
                    <head>
                        <meta charset="UTF-8" />
                        <title>LoPy Config</title>
                    </head>

                    <style type="text/css">
                        * {
                            font-family: monospace;
                            font-size: 18px;
                        }
                        body {
                            
                            padding: 0;
                        }
                        h1 {
                            color: white;
                            background-color: black;
                            font-size: 30px;
                        }
                    </style>

                    <body>
                        
                        <h1>LoPy</h1>
                        <status>
                            <ul>
                                <li>WiFi&nbsp&nbsp&nbsp : ok</li>
                                <li>SSID&nbsp&nbsp&nbsp : LoPy</li>
                                <li>Clients : skuu</li>
                                <li>LoRa&nbsp&nbsp&nbsp : ok</li>
                            </ul> 
                        </status>
            """
        for espid, espip in esp_id_ip.items():
            response += "<esp><p>"+espid+" : <input id=\""+espid+"\" type=\"text\"> <button onclick=\"sendText(\""+espid+"\",\""+espip+"\")\">Send</button></p></esp>"
                        
                        
        response +="""\
                    </body>
                
                    <script type="text/javascript">
                        function sendText(espid, espip){
                            var text = document.getElementById(espid).value;
                            var xhr = new XMLHttpRequest();
                            var url = "http://"+espip+"/cm?user=admin&password=azerty&cmnd=Displaytext [zs2]"+text;
                            xhr.open("GET", url, true);
                            xhr.setRequestHeader("Content-Type", "application/json");
                            xhr.onreadystatechange = function () {
                                if (xhr.readyState === 4 && xhr.status === 200) {
                                    var json = JSON.parse(xhr.responseText);
                                    console.log(json);
                                }
                            };
                            xhr.send();
                        };
                    </script>
                
                </html>

            """
        httpResponse.WriteResponseOk(
            headers = None,
            contentType = "text/html",
            contentCharset = "UTF-8",
            content = response
        )

        
mws = MicroWebSrv() # TCP port 80 and files in /flash/www
mws.Start(threaded=True)         # Starts server in a new

############################################################################


################################ MAIN LOOP #################################
_join()
while True:
    time.sleep(5)
    request = {}
    request["esp_subscribed"] = esp_subscribed
    encoded = ujson.dumps(request)
    send(encoded)
    Led.blink_green()
    time.sleep(10)
############################################################################
