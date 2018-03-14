#!/usr/bin/env python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2014             mk@mathias-kettner.de |
# +------------------------------------------------------------------+
#
# This file is part of Check_MK.
# The official homepage is at http://mathias-kettner.de/check_mk.
#
# check_mk is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# tails. You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.

import pyghmi.ipmi.command as ipmi_cmd
import pyghmi.ipmi.sdr as ipmi_sdr
import pyghmi.constants as ipmi_const
from pyghmi.exceptions import IpmiException

import cmk.debug

import cmk_base.config as config
import cmk_base.checks as checks
from cmk_base.exceptions import MKAgentError

from .abstract import CheckMKAgentDataSource, ManagementBoardDataSource


class IPMIManagementBoardDataSource(ManagementBoardDataSource, CheckMKAgentDataSource):

    def id(self):
        return "mgmt_ipmi"


    def title(self):
        return "Management board - IPMI"


    def describe(self):
        return "%s (Address: %s, User: %s)" % (
            self.title(),
            self._ipaddress,
            self._credentials()["username"],
        )


    def _cpu_tracking_id(self):
        return self.id()


    def _gather_check_plugin_names(self, *args, **kwargs):
        return ["mgmt_ipmi_sensors"]


    def _execute(self):
        try:
            connection = self._create_ipmi_connection()

            output = ""
            output += self._fetch_ipmi_sensors_section(connection)
            output += self._fetch_ipmi_firmware_section(connection)

            return output
        except Exception, e:
            if cmk.debug.enabled():
                raise

            # Improve bad exceptions thrown by pyghmi e.g. in case of connection issues
            if type(e) == IpmiException and "%s" % e == "None":
                raise MKAgentError("IPMI communication failed")
            else:
                raise


    def _create_ipmi_connection(self):
        # Do not use the (custom) ipaddress for the host. Use the management board
        # address instead
        credentials = self._credentials()

        return ipmi_cmd.Command(bmc=self._ipaddress,
                               userid=credentials["username"],
                               password=credentials["password"])


    def _fetch_ipmi_sensors_section(self, connection):
        self._logger.debug("[%s] Fetching sensor data via UDP from %s:623" % (self.id(), self._ipaddress))
        sdr = ipmi_sdr.SDR(connection)
        sensors = []
        for number in sdr.get_sensor_numbers():
            rsp = connection.raw_command(command=0x2d, netfn=4, data=(number,))
            if 'error' in rsp:
                continue

            reading = sdr.sensors[number].decode_sensor_reading(rsp['data'])
            if reading is None:
                continue

            # {'states': [], 'health': 0, 'name': 'CPU1 Temp', 'imprecision': 0.5,
            #  'units': '\xc2\xb0C', 'state_ids': [], 'type': 'Temperature',
            #  'value': 25.0, 'unavailable': 0}]]
            health_txt = "N/A"
            if reading.health >= ipmi_const.Health.Failed:
                health_txt = "FAILED"
            elif reading.health >= ipmi_const.Health.Critical:
                health_txt = "CRITICAL"
            elif reading.health >= ipmi_const.Health.Warning:
                health_txt = "WARNING"
            elif reading.health == ipmi_const.Health.Ok:
                health_txt = "OK"

            parts = [
                "%d" % number,
                reading.name,
                reading.type,
                ("%0.2f" % reading.value) if reading.value else "N/A",
                reading.units if reading.units != "\xc2\xb0C" else "C",
                health_txt,
            ]

            sensors.append(parts)

        output = "<<<mgmt_ipmi_sensors:sep(124)>>>\n" \
               + "".join([ "|".join(sensor) + "\n"  for sensor in sensors ])

        return output


    def _fetch_ipmi_firmware_section(self, connection):
        self._logger.debug("[%s] Fetching firmware information via UDP from %s:623" % (self.id(), self._ipaddress))

        output = "<<<mgmt_ipmi_firmware:sep(124)>>>\n"
        for entity_name, attributes in connection.get_firmware():
            for attribute_name, value in attributes.items():
               output += "%s|%s|%s\n" % (entity_name, attribute_name, value)

        return output


    def _summary_result(self):
        return 0, "Version: %s" % self._get_ipmi_version(), []


    def _get_ipmi_version(self):
        section = self._host_sections.sections.get("mgmt_ipmi_firmware")
        if not section:
            return "unknown"

        for line in section:
            if line[0] == "BMC Version" and line[1] == "version":
                return line[2]

        return "unknown"
