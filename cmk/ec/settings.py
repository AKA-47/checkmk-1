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
"""Settings handling for the Check_MK event console."""

from __future__ import print_function

# NOTE: pylint/astroid doesn't fully understand typing annotations and the
# typing module yet, so we may have to suppress some things, see e.g. the
# issues https://github.com/PyCQA/pylint/issues/1063 for unused-import and
# https://github.com/PyCQA/pylint/issues/1290 for invalid-name.

from argparse import ArgumentParser, ArgumentTypeError, RawDescriptionHelpFormatter
from pathlib2 import Path
from typing import List, NamedTuple, Optional, Union  # pylint: disable=unused-import


# a filesystem path with a user-presentable description
AnnotatedPath = NamedTuple(
    'AnnotatedPath', [('description', str),
                      ('value', Path)])


# filesystem paths related to the event console
Paths = NamedTuple(
    'Paths', [('main_config_file', AnnotatedPath),
              ('config_dir', AnnotatedPath),
              ('unix_socket', AnnotatedPath),
              ('event_socket', AnnotatedPath),
              ('event_pipe', AnnotatedPath),
              ('pid_file', AnnotatedPath),
              ('log_file', AnnotatedPath),
              ('state_dir', AnnotatedPath),
              ('compiled_mibs_dir', AnnotatedPath),
              ('mongodb_config_file', AnnotatedPath)])


def default_paths(omd_root, default_config_dir):
    # type: (Path, Path) -> Paths
    """Returns all default filesystem paths related to the event console"""
    return Paths(
        main_config_file=AnnotatedPath('main configuration',
                                       default_config_dir / 'mkeventd.mk'),
        config_dir=AnnotatedPath('configuration directory',
                                 default_config_dir / 'mkeventd.d'),
        unix_socket=AnnotatedPath('Unix socket',
                                  omd_root / 'tmp/run/mkeventd/status'),
        event_socket=AnnotatedPath('event socket',
                                   omd_root / 'tmp/run/mkeventd/eventsocket'),
        event_pipe=AnnotatedPath('event pipe',
                                 omd_root / 'tmp/run/mkeventd/events'),
        pid_file=AnnotatedPath('PID file', omd_root / 'tmp/run/mkeventd/pid'),
        log_file=AnnotatedPath('log file', omd_root / 'var/log/mkeventd.log'),
        state_dir=AnnotatedPath('state directory', omd_root / 'var/mkeventd'),
        compiled_mibs_dir=AnnotatedPath('compiled MIBs directory',
                                        omd_root / 'local/share/check_mk/compiled_mibs'),
        mongodb_config_file=AnnotatedPath('MongoDB configuration', omd_root / 'etc/mongodb.conf'))


# a network port number
PortNumber = NamedTuple('PortNumber', [('value', int)])


# network port numbers related to the event console
PortNumbers = NamedTuple(
    'PortNumbers', [('syslog_udp', PortNumber),
                    ('syslog_tcp', PortNumber),
                    ('snmptrap_udp', PortNumber)])


def default_port_numbers():
    # type: () -> PortNumbers
    """Returns all port numbers related to the event console"""
    return PortNumbers(syslog_udp=PortNumber(514),
                       syslog_tcp=PortNumber(514),
                       snmptrap_udp=PortNumber(162))


# a Unix file descriptor number
FileDescriptor = NamedTuple('FileDescriptor', [('value', int)])


class ECArgumentParser(ArgumentParser):

    """An argument parser for the event console"""

    def __init__(self, prog, version, paths, port_numbers):
        # type: (str, str, Paths, PortNumbers) -> None
        super(ECArgumentParser, self).__init__(
            prog=prog,
            formatter_class=RawDescriptionHelpFormatter,
            description='Start the Check_MK event console.',
            epilog=self._epilog(paths))
        self._add_arguments(version, port_numbers)

    @staticmethod
    def _epilog(paths):
        # type: (Paths) -> str
        width = max([len(p.description) for p in paths]) + 1  # for colon
        return ('Paths used by the event console:\n\n' +
                '\n'.join('  {:<{width}} {}'.format(p.description + ':', p.value, width=width)
                          for p in paths))

    def _add_arguments(self, version, port_numbers):
        # type: (str, PortNumbers) -> None
        self.add_argument(
            '-V', '--version', action='version', version='%(prog)s version ' + version)
        self.add_argument(
            '-v', '--verbose', action='count', default=0, help='increase verbosity')
        self.add_argument(
            '--syslog', action='store_true', help='enable built-in UDP syslog server')
        self.add_argument(
            '--syslog-fd', metavar='FD', type=self._file_descriptor,
            help=('use the given file descriptor instead of UDP port %d' %
                  port_numbers.syslog_udp.value))
        self.add_argument(
            '--syslog-tcp', action='store_true', help='enable built-in TCP syslog server')
        self.add_argument(
            '--syslog-tcp-fd', metavar='FD', type=self._file_descriptor,
            help=('use the given file descriptor instead of TCP port %d' %
                  port_numbers.syslog_tcp.value))
        self.add_argument(
            '--snmptrap', action='store_true', help='enable built-in snmptrap server')
        self.add_argument(
            '--snmptrap-fd', metavar='FD', type=self._file_descriptor,
            help=('use the given file descriptor instead of UDP port %d' %
                  port_numbers.snmptrap_udp.value))
        self.add_argument('-g', '--foreground', action='store_true',
                          help='run in the foreground instead of daemonizing')
        self.add_argument('-d', '--debug', action='store_true',
                          help='enable debug mode, letting exceptions through')
        self.add_argument('--profile-status', action='store_true',
                          help='create performance profile for status thread')
        self.add_argument('--profile-event', action='store_true',
                          help='create performance profile for event thread')

    @staticmethod
    def _file_descriptor(value):
        # type: (str) -> FileDescriptor
        """A custom argument type for file descriptors, i.e. non-negative integers"""
        try:
            file_desc = int(value)
            if file_desc < 0:
                raise ValueError
        except ValueError:
            raise ArgumentTypeError(
                'invalid file descriptor value: %r' % value)
        return FileDescriptor(file_desc)


# a communication endpoint, e.g. for syslog or SNMP
EndPoint = Union[PortNumber, FileDescriptor]  # pylint: disable=invalid-name


def _endpoint(enabled, file_descriptor, default_port_number):
    # type: (bool, FileDescriptor, PortNumber) -> Optional[EndPoint]
    """Returns a communication endpoint based on given commandline arguments"""
    if not enabled:
        return None
    if file_descriptor is None:
        return default_port_number
    return file_descriptor


# various post-processed commandline options
Options = NamedTuple(
    'Options', [('verbosity', int),
                ('syslog_udp', Optional[EndPoint]),
                ('syslog_tcp', Optional[EndPoint]),
                ('snmptrap_udp', Optional[EndPoint]),
                ('foreground', bool),
                ('debug', bool),
                ('profile_status', bool),
                ('profile_event', bool)])


# all settings of the event console
Settings = NamedTuple(
    'Setting', [('paths', Paths),
                ('options', Options)])


def settings(version, omd_root, default_config_dir, argv):
    # type: (str, Path, Path, List[str]) -> Settings
    """Returns all event console settings"""
    paths = default_paths(omd_root, default_config_dir)
    port_numbers = default_port_numbers()
    parser = ECArgumentParser(Path(argv[0]).name, version, paths, port_numbers)
    args = parser.parse_args(argv[1:])
    options = Options(
        verbosity=args.verbose,
        syslog_udp=_endpoint(
            args.syslog, args.syslog_fd, port_numbers.syslog_udp),
        syslog_tcp=_endpoint(
            args.syslog_tcp, args.syslog_tcp_fd, port_numbers.syslog_tcp),
        snmptrap_udp=_endpoint(
            args.snmptrap, args.snmptrap_fd, port_numbers.snmptrap_udp),
        foreground=args.foreground,
        debug=args.debug,
        profile_status=args.profile_status,
        profile_event=args.profile_event)
    return Settings(paths=paths, options=options)


if __name__ == "__main__":
    import sys
    import cmk
    import cmk.paths
    print(settings(cmk.__version__, Path(cmk.paths.omd_root),
                   Path(cmk.paths.default_config_dir), sys.argv))
