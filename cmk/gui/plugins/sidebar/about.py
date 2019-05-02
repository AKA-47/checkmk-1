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

from cmk.gui.i18n import _
from cmk.gui.globals import html
from . import SidebarSnapin, snapin_registry, bulletlink


@snapin_registry.register
class About(SidebarSnapin):
    @staticmethod
    def type_name():
        return "about"

    @classmethod
    def title(cls):
        return _("About Check_MK")

    @classmethod
    def description(cls):
        return _("Links to webpage, documentation and download of Check_MK")

    def show(self):
        html.open_ul()
        bulletlink(_("Homepage"), "https://checkmk.com/check_mk.html", target="_blank")
        bulletlink(_("Documentation"), "https://checkmk.com/cms.html", target="_blank")
        bulletlink(_("Download"), "https://checkmk.com/download.php", target="_blank")
        html.close_ul()
