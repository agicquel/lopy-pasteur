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
from lora import * 

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
esp_id_ip = {}
############################################################################


############################## Configure LoRa ##############################
lora = LoRa(mode=LoRa.LORAWAN, region=LoRa.EU868)
lopyMAC = ubinascii.hexlify(lora.mac()).upper().decode('utf-8')

messageReceived = False
lopy_connected = False
lora_req_index = 0
lora_req_queue = []
lora_req_current = None
lora_is_fetching = False
lora_selection = ""
lora_fetching_data = ""

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
    global lora_req_index
    global esp_messages_displayed
    global messageReceived

    message = message.decode()
    message = bytes(message, 'utf-8')
    Log.i("message decode : " + str(message))
    message = list(message)
    Log.i("message list : " + str(message))
    
    parsed_index = int(message[0])
    parsed_order = int(message[1]) if len(message) > 1 else config.ORDER_API_EMPTY

    if lora_req_index == 0 and parsed_index != 0:
        Log.i("callback - 2")
        return
    elif lora_req_index == parsed_index:
        messageReceived = True
        Log.i("callback - 3")
        
        if lora_req_index == 0:
            Log.i("callback - 2")
            lora_req_index = lora_req_index + 1
            return
        
        lora_req_index = 1 if lora_req_index >= 255 else (lora_req_index + 1)
        if parsed_order == config.ORDER_API_EMPTY:
            Log.i("callback : received empty order, nothing to do")
        else: # parsed_order in config.ORDER_API_FETCHING:
            _execute_lora_order(message)
            #lora_fetching_data = message[2::]
            #Log.i(lora_fetching_data)
            # if parsed_order in [config.ORDER_DISPLAY_SELECTION[1]]:
            #     lora_is_fetching = True
            # elif parsed_order == config.ORDER_API_FETCHING[3]:
            #     lora_is_fetching = False

def _execute_lora_order(request):
    global lora_is_fetching
    global lora_selection
    global lora_fetching_data
    global esp_messages_displayed
    global lora_req_queue
    order = int(request[1])
    
    if order in [config.ORDER_DISPLAY_SELECTION[0], config.ORDER_DISPLAY_MESSAGE[0]]:
        lora_is_fetching = False
        lora_fetching_data = ""
        for i in range(2, len(request)):
            lora_fetching_data += chr(request[i])
        Log.i("1/ = " + str(lora_fetching_data))
    elif order in [config.ORDER_DISPLAY_SELECTION[1], config.ORDER_DISPLAY_MESSAGE[1]]:
        lora_is_fetching = True
        lora_fetching_data = ""
        for i in range(2, len(request)):
            lora_fetching_data += chr(request[i])
        Log.i("2/ = " + str(lora_fetching_data))
    elif order in [config.ORDER_DISPLAY_SELECTION[2], config.ORDER_DISPLAY_MESSAGE[2]]:
        lora_is_fetching = True
        for i in range(2, len(request)):
            lora_fetching_data += chr(request[i])
        Log.i("3/ = " + str(lora_fetching_data))
    elif order in [config.ORDER_DISPLAY_SELECTION[2], config.ORDER_DISPLAY_MESSAGE[2]]:
        lora_is_fetching = False
        for i in range(2, len(request)):
            lora_fetching_data += chr(request[i])
        Log.i("4/ = " + str(lora_fetching_data))
    
    if not lora_is_fetching:
        if order in config.ORDER_DISPLAY_SELECTION:
            lora_selection = lora_fetching_data
            lora_is_fetching = True
        if order in config.ORDER_DISPLAY_MESSAGE:
            esp_messages_displayed[lora_selection] = lora_fetching_data
        lora_fetching_data = ""
    else:
        lora_req_queue.insert(0, LoraRequest.create_empty_request())

def _lora_callback(trigger):
    Log.i("_lora_callback")
    global messageReceived
    events = lora.events()
    if(events & LoRa.RX_PACKET_EVENT):
        #messageReceived = True
        socketLora.setblocking(True)
        Log.i("LoRa.RX_PACKET_EVENT")
        Led.blink_blue()
        data = socketLora.recv(256)
        socketLora.setblocking(True)
        _callback(data)
    if(events & LoRa.TX_PACKET_EVENT):
        Log.i("LoRa.TX_PACKET_EVENT")
    if(events & LoRa.TX_FAILED_EVENT):
        Log.i("LoRa.TX_FAILED_EVENT")
        _join()


lora.callback(trigger=(LoRa.RX_PACKET_EVENT | LoRa.TX_PACKET_EVENT |
                       LoRa.TX_FAILED_EVENT), handler=_lora_callback)


def _join():
    global lopy_connected
    if not lora.has_joined():
        Log.i("Connecting Lora...")
        lopy_connected = False
        Led.blink_yellow()
        lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0)
        attempt = 0
        while not lora.has_joined():
            time.sleep(2.5)
            attempt += 1
            if attempt % 30 == 0:
                lora.join(activation=LoRa.OTAA, auth=(app_eui, app_key), timeout=0)
        lopy_connected = True
        Led.blink_green()
        Log.i("Connected")


def send(message):
    message = chr(lora_req_index) + message
    Log.i("Sending : " + str(bytes(message, 'utf-8')))
    global messageReceived
    Led.blink_purple()
    _join()
    messageReceived = False
    attemptCounter = 0

    while(not messageReceived): # and attemptCounter < 3
        socketLora.send(message.encode())
        duty_cycle = DutyCycleCalculator.compute_safe_case(spread_factor=lora.sf())
        Log.i("Duty cycle = " + str(duty_cycle))
        Log.i("Attempt number " + str(attemptCounter))
        
        time.sleep(int(duty_cycle / 1000)*2)
        ## FOR TEST
        #time.sleep(300)
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
    global esp_messages_displayed
    global esp_id_ip
    params = httpClient.GetRequestQueryParams()
    if "espid" in params:
        espid = params["espid"]
        Log.i("new sub espId : " + espid)
        lora_req_queue.append(LoraRequest(orders_id=config.ORDER_DISPLAY_CONNECTION, data=("c" + str(espid))))
        if espid not in esp_subscribed:
            esp_subscribed.append(espid)
        if espid not in esp_messages_displayed:
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
    global lora_req_queue
    params = httpClient.ReadRequestPostedFormData()
    espid = routeArgs['espid']
    message = params["message"]
    if espid in esp_subscribed:
        esp_messages_displayed[espid] = message
        lora_req_queue.append(LoraRequest(orders_id=config.ORDER_DISPLAY_SELECTION, data=(str(espid))))
        lora_req_queue.append(LoraRequest(orders_id=config.ORDER_DISPLAY_MESSAGE, data=(str(message))))
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

############################### ESP REQ LOOP ###############################

def th_reqEsp(delay, id):
    global esp_id_ip
    global esp_subscribed
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
    lora_req_queue.append(LoraRequest(orders_id=config.ORDER_DISPLAY_CONNECTION, data=("d" + str(espid))))
############################################################################


################################ MAIN LOOP #################################
_thread.start_new_thread(th_reqEsp, (20, 1337))
_join()

while not lopy_connected:
    time.sleep(2)

while True:
    if lora_req_current == None:
        if len(lora_req_queue) == 0:
            lora_req_queue.append(LoraRequest.create_empty_request())
        lora_req_current = lora_req_queue.pop(0)

        # FOR TEST
        #time.sleep(1200)

        continue
    elif lora_req_current.is_finished():
        lora_req_current = None
        continue
    else:
        send(lora_req_current.pop_payload())
############################################################################
