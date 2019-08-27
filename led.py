import pycom

class Led:
    @staticmethod
    def blink_red():
        pycom.heartbeat(False)
        pycom.rgbled(0x7f0000)

    @staticmethod
    def blink_yellow():
        pycom.heartbeat(False)
        pycom.rgbled(0xffff00)

    @staticmethod
    def blink_orange():
        pycom.heartbeat(False)
        pycom.rgbled(0xffa500)

    @staticmethod
    def blink_purple():
        pycom.heartbeat(False)
        pycom.rgbled(0x551a8b)

    @staticmethod
    def blink_green():
        pycom.heartbeat(False)
        pycom.rgbled(0x007f00)

    @staticmethod
    def blink_blue():
        pycom.heartbeat(False)
        pycom.rgbled(0x0000FF)
