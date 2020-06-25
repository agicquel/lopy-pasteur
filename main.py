from network import WLAN
from network import LoRa
from microWebSrv import MicroWebSrv
from logger import Log
from led import Led
import machine
import network
import time
import _thread
import config
import ujson
import pycom
from network import Server
import ubinascii
import socket
from microWebCli import MicroWebCli
import os

Log.i("LoPy launched")
Led.blink_red()
time.sleep(10)

################################# INIT #####################################
lopy_ssid = config.WIFI_SSID_PREFIX + \
    ubinascii.hexlify(network.WLAN().mac()[
                      1], ':').decode().replace(":", "")[-5:]
if not config.CONFIGURATION_FILES_DIR in os.listdir():
    os.mkdir(config.CONFIGURATION_FILES_DIR)
try:
    ssid_file = open(config.CONFIGURATION_FILES_DIR + '/ssid', 'r')
    lopy_ssid = ssid_file.read()
    ssid_file.close()
except:
    ssid_file = open(config.CONFIGURATION_FILES_DIR + '/ssid', 'w+')
    ssid_file.write(lopy_ssid)
    ssid_file.close()

Log.i("lopy_ssid = " + lopy_ssid)
############################################################################


############################ Configure ESP vars ############################
esp_subscribed = []
esp_subscribed_lora = []
esp_messages_displayed = {}
esp_messages_lora = {}
esp_id_ip = {}
esp_local_changed = []
############################################################################


############################## Configure LoRa ##############################
lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868)
lopyMAC = ubinascii.hexlify(lora.mac()).upper().decode('utf-8')

messageReceived = False
lopy_connected = False
seq_num = 0
reqLora = {}
reqNextLora = {}
reqLoraInit = {}
reqLoraInit['s'] = 0

lora_monitors_ip = []

socketLora = socket.socket(socket.AF_LORA, socket.SOCK_RAW)
socketLora.setsockopt(socket.SOL_LORA, socket.SO_DR, 5)
socketLora.setsockopt(socket.SOL_LORA, socket.SO_CONFIRMED, False)
socketLora.bind(config.LORA_FPORT)
socketLora.settimeout(60)

app_eui = ubinascii.unhexlify(config.LORA_APP_ID)
app_key = ubinascii.unhexlify(config.LORA_APP_KEY)


def _callback(message):
    Log.i("_callback")
    global seq_num
    global esp_messages_lora
    global esp_messages_displayed
    global reqLora
    global reqNextLora
    if(not messageReceived):
        return
    message = message.decode()
    Log.i("message decode = " + message)
    parsed = ujson.loads(message)
    sendToMonitors(message, "received")

    if seq_num == 0 and parsed['s'] != 0:
        return
    elif seq_num == 0 and parsed['s'] == 0:
        seq_num = seq_num + 1
    elif parsed['s'] == seq_num:
        reqLora.clear()
        seq_num = parsed['s'] + 1
        reqLora = reqNextLora.copy()
        reqNextLora.clear()
        if 'm' in parsed:
            for m in parsed['m']:
                mId = str(m.get("id"))
                mMes = str(m.get("mes"))
                if mId and mMes and not mId in esp_local_changed:
                    if((not mId in esp_messages_lora) or esp_messages_lora[mId] != mMes):
                        esp_messages_lora[mId] = mMes
                        esp_messages_displayed[mId] = mMes
        esp_local_changed.clear()


def _lora_callback(trigger):
    Log.i("_lora_callback")
    global messageReceived
    events = lora.events()
    if(events & LoRa.RX_PACKET_EVENT):
        messageReceived = True
        socketLora.setblocking(True)
        Log.i("LoRa.RX_PACKET_EVENT")
        Led.blink_blue()
        data = socketLora.recv(256)
        socketLora.setblocking(True)
        _callback(data)
    #    if(events & LoRa.TX_PACKET_EVENT):
    #        Log.i("LoRa.TX_PACKET_EVENT")
    if(events & LoRa.TX_FAILED_EVENT):
        Log.i("LoRa.TX_FAILED_EVENT")
        _join()


lora.callback(trigger=(LoRa.RX_PACKET_EVENT |
                       LoRa.TX_FAILED_EVENT), handler=_lora_callback)


def _join():
    global lopy_connected
    if not lora.has_joined():
        Log.i("Connecting Lora...")
        lopy_connected = False
        Led.blink_yellow()
        lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0)
        while not lora.has_joined():
            time.sleep(2.5)
        lopy_connected = True
        Led.blink_green()
        Log.i("Connected")


def send(message):
    sendToMonitors(message, "sent")
    Log.i("Sending : " + message)
    global messageReceived
    Led.blink_purple()
    _join()
    messageReceived = False
    attemptCounter = 0

    while(not messageReceived and attemptCounter < 3):
        socketLora.send(message.encode())
        time.sleep(20)
        attemptCounter = attemptCounter + 1

    Led.blink_green()
    Log.i("Message sent")
############################################################################


############################## Configure Wifi ##############################
wlan = WLAN(mode=WLAN.AP, ssid=lopy_ssid, auth=(
    WLAN.WPA2, config.WIFI_PASS), channel=11, antenna=WLAN.INT_ANT)
wlan.ifconfig(id=1, config=(config.API_HOST,
                            '255.255.255.0', '10.42.31.1', '8.8.8.8'))


def _wlan_callback(trigger):
    Log.i("_wlan_callback")
    Log.i("trigger type = " + type(trigger))
    Log.i("trigger = " + trigger)


wlan.callback(trigger=(WLAN.EVENT_PKT_ANY | WLAN.EVENT_PKT_CTRL | WLAN.EVENT_PKT_DATA | WLAN.EVENT_PKT_DATA_AMPDU |
                       WLAN.EVENT_PKT_DATA_MPDU | WLAN.EVENT_PKT_MISC | WLAN.EVENT_PKT_MGMT), handler=_wlan_callback)
############################################################################


######################### Configure FTP and Telnet #########################
server = network.Server()
server.deinit()  # disable
############################################################################


########################## Configure microWebSrv ###########################
# DOC : https://github.com/jczic/MicroWebSrv

@MicroWebSrv.route('/subscribe', 'POST')
def handlerFuncPost(httpClient, httpResponse):
    global esp_subscribed
    global esp_messages_lora
    global esp_messages_displayed
    global esp_id_ip
    params = httpClient.GetRequestQueryParams()
    if "espid" in params:
        espid = params["espid"]
        Log.i("new sub espId : " + espid)
        if espid not in esp_subscribed:
            esp_subscribed.append(espid)
        if espid not in esp_messages_displayed:
            esp_messages_lora[espid] = espid
            esp_messages_displayed[espid] = espid
        esp_id_ip[espid] = httpClient.GetIPAddr()
        httpResponse.WriteResponseOk(
            headers=None,
            contentType="text/plain",
            contentCharset="UTF-8",
            content="Subscribed"
        )
    else:
        httpResponse.WriteResponseForbidden()


@MicroWebSrv.route('/monitor', 'GET')
def handlerFuncPostMonitor(httpClient, httpResponse):
    global lora_monitors_ip
    lora_monitors_ip.append(httpClient.GetIPAddr())
    httpResponse.WriteResponseOk(
        headers=None,
        contentType="text/plain",
        contentCharset="UTF-8",
        content="Monitoring."
    )


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
    global esp_messages_displayed
    espid = routeArgs['espid']
    if espid in esp_subscribed:
        httpResponse.WriteResponseOk(
            headers=None,
            contentType="text/plain",
            contentCharset="UTF-8",
            content=esp_messages_displayed.get(espid)
        )
    else:
        httpResponse.WriteResponseForbidden()


@MicroWebSrv.route('/')
def handlerFuncGet(httpClient, httpResponse):
    response = """\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8" />
            <title>ESP MESSAGES</title>
            <script>
                    function updateLopy(espid, message) {
                        var data = "message=" + message;
                        var xhr = new XMLHttpRequest();

                        xhr.addEventListener("readystatechange", function () {
                        if (this.readyState === 4) {
                            console.log(this.responseText);
                        }
                        });

                        xhr.open("PUT", "http://""" + config.API_HOST + """/displays/" + espid);
                        xhr.withCredentials = true;
                        xhr.send(data);
                    }
                    function sendText(espid, espip){
                        var text = document.getElementById(espid).value;
                        var cell = document.getElementById("message-" + espid).innerHTML = text;
                        updateLopy(espid, text);
                        var xhr = new XMLHttpRequest();
                        var url = "http://"+espip+"/cm?user=admin&password=azerty&cmnd=Displaytext [z][s2]"+text;
                        xhr.open("GET", url, true);
                        xhr.withCredentials = true;
                        xhr.onreadystatechange = function () {
                            if (xhr.readyState === 4 && xhr.status === 200) {
                                var json = JSON.parse(xhr.responseText);
                                console.log(json);
                            }
                        };
                        xhr.send();
                    };
                    function rename() {
                        var text = document.getElementById("ssid_rename").value;
                        var xhr = new XMLHttpRequest();
                        xhr.withCredentials = true;
                        xhr.addEventListener("readystatechange", function () {
                        if (this.readyState === 4) {
                            console.log(this.responseText);
                        }
                        });
                        xhr.open("GET", "http://10.42.31.2/rename/" + text);
                        xhr.send();
                    }
                </script>
        </head>
        <body>
            <h3>Page de configuration du LoPy</h3>
            <br>
            <ul>
                <li>SSID&nbsp;&nbsp;&nbsp; : """ + lopy_ssid + """ <input id=\"ssid_rename\" type=\"text\"> <button onclick=\'rename()\'>Rename</button></li>
                <li>MAC&nbsp;&nbsp;&nbsp; : """ + lopyMAC + """</li>
                <li>LoRa&nbsp;&nbsp;&nbsp; : """ + ("Connecté" if lopy_connected else "Déconnecté") + """</li>
            </ul> 
            <br>
            <table border="1">
            <thead>
                <tr>
                    <th>ESP ID</th>
                    <th>ESP IP</th>
                    <th>Message</th>
                    <th>Modification</th>
                </tr>
            </thead>
            <tbody>
        """

    for espid, espip in esp_id_ip.items():
        response += "<tr><td>" + espid + "</td>"
        response += "<td><a href=\"http://" + espip + "\">" + espip + "</a></td>"
        response += "<td id='message-" + espid + "'>" + \
            esp_messages_displayed.get(espid) + "</td>"
        response += "<td><input id=\""+espid + \
            "\" type=\"text\"> <button onclick=\'sendText(\"" + \
            espid+"\",\""+espip+"\")\'>Send</button></td></tr>"
    response += """\
                </tbody>
                </table>
                <br>
            </body>
        </html>
        """

    httpResponse.WriteResponseOk(
        headers=None,
        contentType="text/html",
        contentCharset="UTF-8",
        content=response
    )


@MicroWebSrv.route('/displays', 'GET')
def handlerFuncGetDisplays(httpClient, httpResponse):
    response = "["
    for espid, espmes in esp_messages_displayed.items():
        response += '{"message": "' + espmes + '",'
        response += '"name": "Afficheur-' + espid + '",'
        response += '"espId": "' + espid + '"}'
        response += ","
    if(len(response) != 1):
        response = response[:-1]
    response += "]"
    Log.i("response = " + response)
    httpResponse.WriteResponseOk(
        headers=None,
        contentType="application/json",
        contentCharset="UTF-8",
        content=response
    )


@MicroWebSrv.route('/displays/<espid>', 'PUT')
def handlerFuncPost(httpClient, httpResponse, routeArgs):
    global esp_subscribed
    global esp_messages_displayed
    global esp_local_changed
    params = httpClient.ReadRequestPostedFormData()
    espid = routeArgs['espid']
    message = params["message"]
    if espid in esp_subscribed:
        esp_messages_displayed[espid] = message
        esp_local_changed.append(espid)
        httpResponse.WriteResponseOk(
            headers=None,
            contentType="text/plain",
            contentCharset="UTF-8",
            content="Message updated",

        )
    else:
        httpResponse.WriteResponseForbidden()


@MicroWebSrv.route('/rename/<ssid>', 'GET')
def handlerFuncEditSsid(httpClient, httpResponse, routeArgs):
    global lopy_ssid
    global wlan
    lopy_ssid = config.WIFI_SSID_PREFIX + routeArgs["ssid"]
    Log.i("ssid changed : " + lopy_ssid)
    httpResponse.WriteResponseOk(
        headers=None,
        contentType="text/plain",
        contentCharset="UTF-8",
        content="SSID renamed."
    )
    ssid_file = open(config.CONFIGURATION_FILES_DIR + '/ssid', 'w+')
    try:
        ssid_file.write(lopy_ssid)
        ssid_file.close()
    except:
        Log.i("Cant save the new ssid")
    wlan.deinit()
    wlan = WLAN(mode=WLAN.AP, ssid=lopy_ssid, auth=(
        WLAN.WPA2, config.WIFI_PASS), channel=11, antenna=WLAN.INT_ANT)
    wlan.ifconfig(id=1, config=(config.API_HOST,
                                '255.255.255.0', '10.42.31.1', '8.8.8.8'))


mws = MicroWebSrv()  # TCP port 80 and files in /flash/www
mws.Start(threaded=True)         # Starts server in a new
############################################################################

############################## MONITORING REQ ##############################


def sendToMonitors(req: str, typeRequest: str):
    global lora_monitors_ip
    for monitor in lora_monitors_ip:
        wCli = MicroWebCli("http://"+monitor +
                           ":6666/lopyrequests", method='POST')
        try:
            wCli.OpenRequestFormData(
                formData={'type': typeRequest, 'request': ubinascii.b2a_base64(req)})
            buf = memoryview(bytearray(1024))
            resp = wCli.GetResponse()
            if not resp.IsSuccess():
                lora_monitors_ip.remove(monitor)
        except:
            lora_monitors_ip.remove(monitor)

############################################################################

############################### ESP REQ LOOP ###############################


def th_reqEsp(delay, id):
    global esp_id_ip
    global esp_subscribed
    global esp_messages_lora
    global esp_messages_displayed

    while True:
        for espid, espip in esp_id_ip.items():
            Log.i("Envoi de la req pour espid = " + espid + ", ip = " + espip)
            wCli = MicroWebCli("http://"+espip+"/cm")
            wCli.QueryParams['message'] = str(
                esp_messages_displayed.get(espid))
            print('GET %s' % wCli.URL)
            try:
                wCli.OpenRequest()
                buf = memoryview(bytearray(1024))
                resp = wCli.GetResponse()
                if resp.IsSuccess():
                    while not resp.IsClosed():
                        x = resp.ReadContentInto(buf)
                        if x < len(buf):
                            buf = buf[:x]
                else:
                    print('GET return %d code (%s)' %
                          (resp.GetStatusCode(), resp.GetStatusMessage()))
                    removeEsp(espid)
            except:
                removeEsp(espid)
        time.sleep(delay)


def removeEsp(espid):
    esp_subscribed.remove(espid)
    esp_id_ip.pop(espid)
############################################################################


################################ MAIN LOOP #################################
_thread.start_new_thread(th_reqEsp, (20, 1337))
_join()
time.sleep(5)
while True:
    esp_new_discon = []
    esp_new_con = []
    modified = False
    for esp in esp_subscribed_lora:
        if esp not in esp_subscribed:
            esp_new_discon.append(esp)
    for esp in esp_subscribed:
        if esp not in esp_subscribed_lora:
            esp_new_con.append(esp)
    Log.i("esp_subscribed_lora = " + ujson.dumps(esp_subscribed_lora))
    Log.i("esp_new_discon = " + ujson.dumps(esp_new_discon))
    Log.i("esp_new_con = " + ujson.dumps(esp_new_con))
    esp_subscribed_lora = esp_subscribed.copy()

    if len(esp_new_con) != 0:
        reqNextLora['c'] = esp_new_con
        modified = True
    if len(esp_new_discon) != 0:
        reqNextLora['d'] = esp_new_discon
        modified = True

    new_lopy_mes = []
    for esp in esp_subscribed:
        if((esp in esp_messages_lora and esp in esp_messages_displayed) and esp_messages_lora[esp] != esp_messages_displayed[esp]):
            new_lopy_mes.append(
                {"id": esp, "mes": esp_messages_displayed[esp]})
            esp_messages_lora[esp] = esp_messages_displayed[esp]

    if(len(new_lopy_mes) != 0):
        reqNextLora["m"] = new_lopy_mes
        modified = True

    # if modified:
        #seq_num = seq_num + 1

    reqLora['s'] = seq_num

    if seq_num == 0:
        send(ujson.dumps(reqLoraInit))
    else:
        send(ujson.dumps(reqLora))
    Led.blink_green()
    time.sleep(60)
############################################################################
