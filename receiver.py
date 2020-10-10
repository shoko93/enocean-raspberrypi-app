# -----------------------------------------------------------------------------
# Recieve STM 550 sensor data assuming following profile and mode
#
# Profile: D2-14-41, 9-bit VLD Data
# Running in Operation Mode
# -----------------------------------------------------------------------------

import serial
import sys
import json
from azure.iot.device import IoTHubDeviceClient, Message

# Constant Definition
RADIO_ADVANCED = 0x0A

BUFFER_LENGTH = 128
SENSOR_DATA_LENGTH = 15

LEADINGS = 5

# The device connection string to authenticate the device with your IoT hub.
CONNECTION_STRING = ""

# Define the JSON message to send to IoT Hub.
MSG_TXT = '{{"temperature": {temperature}, "humidity": {humidity}}}'

# 8-bit crc
def crc8(data, offset, count):
    with open('json/crc8.json') as f:
        crc8_table = json.load(f)
    crc = 0
    count = count + offset
    for i in range(offset, count):
        crc = int(crc8_table[crc ^ data[i]], 16)
    return crc

# main logic
def run(client):
    
    serial_port = serial.Serial('/dev/ttyUSB0', 57600)

    data_length = 0
    data_offset = 0
    optional_length = 0

    read_buffer = []
    read_buffer.append(0)
    
    header = []
    actual_data = []
    
    tel_type = 0
    packet_type = 0

    got_header = False

    while got_header == False:
        try:
            while read_buffer[0] != 0x55:
                read_buffer = list(serial_port.read(1))
                # retrieve header
                header = list(serial_port.read(4))
                data_length = header[0] << 8 | header[1]
                optional_length = header[2]
                packet_type = header[3]
                # header crc check
                crc8h = list(serial_port.read(1))
                got_header = crc8h[0] == crc8(header, 0, len(header))
        except Exception as e:
            print(str(e))
            return

    if data_length > BUFFER_LENGTH:
        data_length = BUFFER_LENGTH
        optional_length = 0
    elif data_length + optional_length > BUFFER_LENGTH:
        optional_length = BUFFER_LENGTH - data_length

    # retrieve data
    read_buffer = []

    if data_length > 0:
        read_buffer.extend(list(serial_port.read(data_length)))
    
    if optional_length > 0:
        read_buffer.extend(list(serial_port.read(optional_length + 1)))

    # data crc check
    crc8d = read_buffer[data_length + optional_length]
    crc8dtmp = crc8(read_buffer, 0, data_length + optional_length)

    if crc8d != crc8dtmp:
        print("Invalid data CRC")
        return

    if packet_type == RADIO_ADVANCED:

        tel_type = read_buffer[0]

        # 9-bit VLD Data
        if tel_type == 0x24:
            try:
                actual_data_length = data_length - LEADINGS - 1
                actual_data = []
                for i in range(actual_data_length):
                    actual_data.append(read_buffer[LEADINGS + data_offset + i])
                if data_length != SENSOR_DATA_LENGTH:
                    print('Unsupported data length')
                else:
                    data = ""
                    for num in actual_data:
                        data = data + format(num, '08b')
                    sensor_data = format_sensor_data(data)
                    msg_txt_formatted = MSG_TXT.format(temperature=sensor_data["temperature"]["value"], humidity=sensor_data["humidity"]["value"])
                    message = Message(msg_txt_formatted)
                    print(message)
                    client.send_message(message)
            except Exception as e:
                print(str(e))
                return

def format_sensor_data(data):

    sensor_data = {}

    with open('json/sensor_parameter.json') as f:
        parameters = json.load(f)
    
    for sensor_parameter in parameters:
        for params in sensor_parameter.values():
            binary = data[params["offset"]:params["offset"] + params["size"]]
            slope = calc_slope(
                params["range"]["min"], float(params["scale"]["min"]),
                params["range"]["max"], float(params["scale"]["max"])
            )
            offset = calc_offset(
                params["range"]["min"], float(params["scale"]["min"]),
                params["range"]["max"], float(params["scale"]["max"])
            )
            partial_data = int(binary, 2)
            sensor_value = partial_data * slope + offset
            label = list(sensor_parameter.keys())[0]
            sensor_data[label] = {
                "value": sensor_value,
                "unit" : params["unit"]
            }

    return sensor_data

# helper functions for calculating sensor values
def calc_slope(x1, y1, x2, y2):
    return float(y1 - y2) / float(x1 - x2)

def calc_offset(x1, y1, x2, y2):
    return float(x1 * y2) - float(x2 * y1) / float(x1 - x2)

# printing sensor data for debugging
def print_sensor_data(sensor_data):
    for key, data in sensor_data.items():
        print(key + ": " + f'{data["value"]:.2f}' + " [" + data["unit"] + "]")
    print("*****************************")
    
if __name__ == "__main__":
    try:
        client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
    except Exception as e:
        print(str(e))
        sys.exit()
    while True:
        try:
            run(client)
        except KeyboardInterrupt:
            print('stop')
            break
