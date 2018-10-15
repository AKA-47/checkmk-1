#!/usr/bin/python
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

import logging as _logging

import cmk.log
import cmk.paths

from cmk.gui.i18n import _

class CMKWebLogger(_logging.getLoggerClass()):
    def exception(self, *args, **kwargs):
        """Logs an optional message together with the traceback of the
        last exception to the current logger (-> web.log)"""
        # FIXME: Ugly Kung Fu to make the msg positional argument optional. This
        # is a consequence of the cruel hack to change exceptions's signature,
        # something which we shouldn't do: Either fix all the call sites or
        # introduce another method.
        if args:
            msg = args[0]
            args = args[1:]
        else:
            msg = _('Internal error')
        msg = kwargs.pop('msg', msg)

        from cmk.gui.globals import html
        if html.in_html_context():
            msg = "%s %s" % (html.request.requested_url, msg)

        super(CMKWebLogger, self).exception(msg, *args, **kwargs)


_logging.setLoggerClass(CMKWebLogger)


logger = cmk.log.get_logger("web")


def init_logging():
    _setup_web_log_logging()


def _setup_web_log_logging():
    del logger.handlers[:] # First remove all handlers

    handler = _logging.FileHandler("%s/web.log" % cmk.paths.log_dir,
                                   encoding="UTF-8")

    handler.setFormatter(cmk.log.get_formatter())
    logger.addHandler(handler)


def set_log_levels(log_levels):
    for logger_name, level in log_levels.items():
        _logging.getLogger(logger_name).setLevel(level)
