# Data configuration
CONFIGURATION_FILES_DIR = 'configuration'

# Wi-Fi configuration
WIFI_SSID_PREFIX = 'Lopy_HP_'
WIFI_PASS = 'lopylopy'

# FTP configuration
FTP_USER = "lopy"
FTP_PASS = "lopylopy"

# LoRa configuration
LORA_FPORT = 2
LORA_APP_ID = "80b3d54991206c90"
LORA_APP_KEY = "17045194819766765333783783225198"

# API general configuration
API_PORT = 1337
API_HOST = '10.42.31.2'
API_ROOT_CA = '/flash/cert/root.pem'
API_CLIENT_CERT = '/flash/cert/cert.pem'
API_PRIVATE_KEY = '/flash/cert/privkey.pem'

# Lora Request orders
ORDER_EMPTY = 0
ORDER_API_EMPTY = 0
#                             [1req,  begin,  load,   end]
ORDER_DISPLAY_CONNECTION    = [2,     3,      4,      5]
ORDER_DISPLAY_SELECTION     = [6,     7,      8,      9]
ORDER_DISPLAY_MESSAGE       = [10,    11,     12,     13]