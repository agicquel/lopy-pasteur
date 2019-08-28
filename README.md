# Source code for LoPy

The purpose of this program is to make the link between the LoRa network and the displays of the Hôtel Pasteur.

## How does it work ?
The ESP chips installed in each display can join the Wifi network of a LoPy. Once the ESP is connected, it has to subscribe and send its ID. Then, the LoPy will request the API through the LoRa network in order to receive the corrects messages.

## Led status
| Color | Status |
|--|--|
| RED | Start up of the LoPy |
| GREEN | Connected to the LoRa network and everything is correct. |
| YELLOW | LoRa network connection in progress. |
| BLUE | Receiving a message through the LoRa network. |
| PURPLE | Sending a message through the LoRa network. |


