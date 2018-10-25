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

import base64
import os
import sys

import cmk.paths

import cmk_base.config as config
import cmk_base.console as console


def do_donation():
    donate = []
    cache_files = os.listdir(cmk.paths.tcp_cache_dir)
    for host in config.all_active_realhosts():
        if config.in_binary_hostlist(host, config.donation_hosts):
            for f in cache_files:
                if f == host or f.startswith("%s." % host):
                    donate.append(f)

    if not donate:
        console.error("No hosts specified. You need to set donation_hosts in main.mk.\n")
        sys.exit(1)

    console.verbose("Donating files %s\n" % " ".join(cache_files))
    indata = base64.b64encode(
        os.popen(
            "tar czf - -C %s %s" % (cmk.paths.tcp_cache_dir, " ".join(donate))).read())  # nosec

    output = os.popen(config.donation_command, "w")  # nosec
    output.write("\n\n@STARTDATA\n")
    while len(indata) > 0:
        line = indata[:64]
        output.write(line)
        output.write('\n')
        indata = indata[64:]
