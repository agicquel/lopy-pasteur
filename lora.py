import math
from logger import Log
import config

class CodingRate:
    CR1 = "4/5"
    CR2 = "4/6"
    CR3 = "4/7"
    CR4 = "4/8"

class AirtimeCalculator:
    # Calculates the LoRa airtime in milliseconds
    # doc of the equations: https://lora-developers.semtech.com/library/product-documents/ in AN1200.13 "LoRa Modem Designer’s Guide"
    @staticmethod
    def computeAirTime(packet_size: int, spread_factor: int, bandwidth: int = 125, coding_rate: str = CodingRate.CR1, explicit_header: bool = True, preamble_length: int = 8) -> int:
        # All times in milliseconds
        tSym = pow(2, spread_factor) / (bandwidth * 1000) * 1000
        tPreamble = (preamble_length + 4.25) * tSym

        # H = 0 when the header is enabled, H = 1 when no header is present.
        h = 0 if explicit_header else 1

        # Low data rate optimization only for SF11 and SF12, on 125kHz.
        low_data_rate_optimization = 1 if (bandwidth == 125 and spread_factor >= 11) else 0

        # CR is the coding rate from 1 to 4
        cr = int(coding_rate[2]) - 4;
        payloadSymbNb = 8 + max(math.ceil((8 * packet_size - 4 * spread_factor + 28 + 16 - 20 * h) / (4 * (spread_factor - 2 * low_data_rate_optimization))) * (cr + 4), 0)
        tPayload = payloadSymbNb * tSym;
        
        return round(tPreamble + tPayload)

class DutyCycleCalculator:
    # Calculate the duty cycle in miliseconds depending on the spread factor. Even add 20% to be safe
    # Can be improvised with real request scheduling
    @staticmethod
    def compute_safe_case(spread_factor: int) -> int:
        Log.i("compute_safe_case : spread_factor = " + str(spread_factor))
        max_air_time = AirtimeCalculator.computeAirTime(packet_size=LoraRequest.PAYLOAD_MAX_SIZE, spread_factor=spread_factor)
        return round(DutyCycleCalculator.compute_by_airtime(max_air_time) * 1.2)

    @staticmethod
    def compute_by_airtime(airtime: int) -> int:
        return round((airtime / 600) * 60) * 1000
    

class LoraRequest:
    PAYLOAD_OVERHEAD = 13
    PAYLOAD_MAX_SIZE = 50

    # orders_id : [1req, begin, load, end]
    # data : data to upload
    def __init__(self, orders_id: list[int], data: str):
        assert len(orders_id) == 4
        self.bytes_sent = 0
        self.orders_id = orders_id
        self.data = [ord(c) for c in data]
        self.bytes_sent = 0
        self.finished = False

    def pop_payload(self) -> str:
        if self.finished == True:
            return ""

        payload_final_size = self.PAYLOAD_MAX_SIZE - self.PAYLOAD_OVERHEAD
        payload = ""

        Log.i("byte already sent = " + str(self.bytes_sent))

        if self.bytes_sent == 0:
            if len(self.data) <= payload_final_size:
                Log.i("cas 1")
                payload += chr(self.orders_id[0])
                for c in self.data:
                    payload += chr(c)
                self.bytes_sent = len(self.data)
                self.finished = True
            else:
                Log.i("cas 2")
                payload += chr(self.orders_id[1])
                for c in self.data[0:payload_final_size]:
                    payload += chr(c)
                self.bytes_sent = len(str(self.data[0:payload_final_size]))
        else:
            if len(self.data[self.bytes_sent::]) <= payload_final_size:
                Log.i("cas 3")
                payload += chr(self.orders_id[3])
                for c in self.data[self.bytes_sent::]:
                    payload += chr(c)
                self.bytes_sent += len(self.data[self.bytes_sent::])
                self.finished = True
            else:
                Log.i("cas 4")
                payload += chr(self.orders_id[2])
                for c in self.data[self.bytes_sent:(self.bytes_sent + payload_final_size)]:
                    payload += chr(c)
                self.bytes_sent += len(self.data[self.bytes_sent:(self.bytes_sent + payload_final_size)])
        
        return payload

    def is_finished(self) -> bool:
        return self.finished

    @staticmethod
    def create_empty_request() -> LoraRequest :
        return LoraRequest.create_1req_request(config.ORDER_EMPTY, "")

    @staticmethod
    def create_1req_request(order: int, data: str = "") -> LoraRequest :
        assert len(data) < (LoraRequest.PAYLOAD_MAX_SIZE - LoraRequest.PAYLOAD_OVERHEAD)
        return LoraRequest(orders_id=[order, order, order, order], data=data)

