#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
socat /dev/ttyUSB0,raw,echo=0 SYSTEM:'tee in.txt |socat - \
    "PTY,link=/tmp/ttyUSB0,raw,echo=0,waitslave"|tee out.txt'
"""

import csv
import logging
import socket
import sys
import time

from contextlib import contextmanager

from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.exceptions import ConnectionException
from pymodbus.exceptions import ModbusIOException


logging.basicConfig(
    format='%(asctime)s %(levelname)s:%(message)s',
    filename='debugger.log',
    level=logging.INFO)
logging.info('Enter script')

PORT = '/dev/ttyUSB0'  # '/tmp/ttyUSB0'
CSVFILE = 'inverter.csv'
READ_INTERVAL_SECS = 1  # Read the inverter every second.
#NUM_OF_SECS_TO_RUN = 5
WRITE_AT_SECS = 60*10  # Write the readings to CSV every 10 minutes.
TRY_RECONNECT_INTERVAL_SECS = 60  # Try a reconnect with the inverter every 60
                                  # seconds.
MODBUS_SETTINGS = {
    'method': 'rtu',
    'port': PORT,
    'baudrate': 9600,
    'stopbits': 1,
    'parity': 'N',
    'bytesize': 8,
    'timeout': 1,
}


def get_lock(process_name):
    """Without holding a reference to our socket somewhere it gets garbage
    collected when the function exits.
    """
    get_lock._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    try:
        get_lock._lock_socket.bind('\0' + process_name)
        logging.info("I got the lock.")
    except socket.error:
        # TODO LOG PID
        logging.warning("Lock already exists, exiting script.")
        sys.exit()


class Readings:
    """Singleton class to hold readings in memory and periodically save them to
    file.
    """
    __readings = []

    def __empty_readings(self):
        self.__readings = []

    def add_reading(self, reading):
        self.__readings.append(reading)

    def append_to_csv(self):
        logging.info('Writing %i readings to file.' % WRITE_AT_SECS)
        time1 = time.time()
        with open(CSVFILE, 'a', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(self.__readings)
        self.__empty_readings()
        time2 = time.time()
        logging.info(
            "Writing readings to file took: %0.3f ms" % (
                (time2 - time1) * 1000.0))


def read_from_inverter(inverter):
    readings = Readings()

    no_readings = 0
    while True:  # i != NUM_OF_SECS_TO_RUN+1:
        no_readings += 1
        try:
            reading = inverter.read_input_registers(0, 45)
            if isinstance(reading, Exception):
                raise reading
            else:
                reading = reading.registers
        except ModbusIOException as e:
            # Write one last time in case connection is lost.
            logging.error(e)
            logging.warning(
                "Lost connection with inverter, writing readings one last "
                "time.")
            readings.append_to_csv()
            logging.info("Finished writing final results to CSV.")
            break
        else:
            # Add a unix timestamp
            timestamp = time.time()
            reading.append(round(time.time()*1000.0))
            # Add reading to readings in memory
            readings.add_reading(reading)
            # Write to CSV every WRITE_AT_SECS seconds
            if (no_readings%WRITE_AT_SECS) == 0:
                readings.append_to_csv()
            # Read the inverter every READ_INTERVAL_SECS second
            time.sleep(READ_INTERVAL_SECS)
    return None


@contextmanager
def connect_to_inverter():
    try:
        with ModbusClient(**MODBUS_SETTINGS) as inverter:
            logging.info('Connected, start reading from inverter...')
            yield inverter
            logging.info("Stopped reading from inverter.")
    except ConnectionException as e:
        logging.warning(
            "Did not manage to obtain a connection with the inverter.")
    finally:
        logging.warning("Lost connection with inverter.")


if __name__ == '__main__':
    get_lock('reading_inverter')
    while True:
        with connect_to_inverter() as inverter:
            read_from_inverter(inverter)
        logging.info(
            "Trying to reconnect to the inverter in %i seconds." % (
                TRY_RECONNECT_INTERVAL_SECS))
        time.sleep(TRY_RECONNECT_INTERVAL_SECS)
        logging.info("Trying to reconnect to the inverter...")