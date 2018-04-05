#!/usr/bin/env python
# encoding: utf-8

import pytest
import time
import ast
import pathlib2 as pathlib
from testlib import CMKEventConsole, ec, web

import cmk.ec.settings
import cmk.paths
import cmk.ec.main

class FakeStatusSocket(object):
    def __init__(self, query):
        self._query = query
        self._sent = False
        self._response = ""

    def recv(self, size):
        if self._sent:
            return ""

        self._sent = True
        return self._query

    def sendall(self, data):
        self._response += data

    def close(self):
        pass

    def get_response(self):
        response = ast.literal_eval(self._response)
        assert type(response) == list
        return response


@pytest.fixture(scope="function")
def settings():
    return cmk.ec.settings.settings(
        '1.2.3i45',
        pathlib.Path(cmk.paths.omd_root),
        pathlib.Path(cmk.paths.default_config_dir),
        ['mkeventd'])


@pytest.fixture(scope="function")
def config(settings):
    # TODO: Currently does not work as unit test
    cmk.ec.main.load_configuration(settings)


@pytest.fixture(scope="function")
def perfcounters():
    return cmk.ec.main.Perfcounters()


@pytest.fixture(scope="function")
def event_status(settings, perfcounters):
    return cmk.ec.main.EventStatus(settings, perfcounters)


@pytest.fixture(scope="function")
def status_server(settings, config, perfcounters, event_status):
    cmk.ec.main.g_status_server = cmk.ec.main.StatusServer(settings, perfcounters, event_status)
    return cmk.ec.main.g_status_server


def test_handle_client(status_server, event_status):
    s = FakeStatusSocket("GET events")

    status_server.handle_client(s, True, "127.0.0.1")

    response = s.get_response()
    assert len(response) == 1
    assert "event_id" in response[0]


def test_mkevent_check_query_perf(config, status_server, event_status, perfcounters):
    for num in range(10000):
        event_status.new_event(CMKEventConsole.new_event({
            "host": "heute-%d" % num,
            "text": "%s %s BLA BLUB DINGELING ABASD AD R#@A AR@AR A@ RA@R A@RARAR ARKNLA@RKA@LRKNA@KRLNA@RLKNA@äRLKA@RNKAL@R" \
                    " j:O#A@J$ KLA@J $L:A@J :AMW: RAMR@: RMA@:LRMA@ L:RMA@ :AL@R MA:L@RM A@:LRMA@ :RLMA@ R:LA@RMM@RL:MA@R: AM@" % \
                    (time.time(), num),
        }))

    assert len(event_status.events()) == 10000

    s = FakeStatusSocket("GET events\n"
        "Filter: event_host in heute-1 127.0.0.1 heute123\n"
        "Filter: event_phase in open ack\n"
        #"OutputFormat: plain\n"
        #"Filter: event_application ~~ xxx\n"
    )

    before = time.time()

    #import cProfile, StringIO, pstats
    #pr = cProfile.Profile()
    #pr.enable()
    status_server.handle_client(s, True, "127.0.0.1")
    #pr.disable()
    #ps = pstats.Stats(pr, stream=StringIO.StringIO())
    #ps.dump_stats("/tmp/test_mkevent_check_query_perf.profile")

    duration = time.time() - before

    response = s.get_response()
    assert len(response) == 2
    assert "event_id" in response[0]

    assert duration < 0.2


#
# INTEGRATION TESTS
#


def ensure_core_and_get_connection(site, ec, core):
    if core != None:
        site.set_config("CORE", core, with_restart=True)
        live = site.live
    else:
        live = ec.status

    return live


@pytest.mark.parametrize(("core"), [ "nagios", "cmc" ])
def test_command_reload(site, ec, core):
    print "Checking core: %s" % core

    live = ensure_core_and_get_connection(site, ec, core)

    old_t = live.query_value("GET eventconsolestatus\nColumns: status_config_load_time\n")
    print "Old config load time: %s" % old_t
    assert old_t > time.time() - 86400

    time.sleep(1) # needed to have at least one second after EC start
    live.command("[%d] EC_RELOAD" % (int(time.time())))
    time.sleep(1) # needed to have at least one second after EC reload

    new_t = live.query_value("GET eventconsolestatus\nColumns: status_config_load_time\n")
    print "New config load time: %s" % old_t
    assert new_t > old_t


# core == None means direct query to status socket
@pytest.mark.parametrize(("core"), [ None, "nagios", "cmc" ])
def test_status_table_via_core(site, ec, core):
    print "Checking core: %s" % core

    live = ensure_core_and_get_connection(site, ec, core)
    if core == None:
        result = live.query_table_assoc("GET status\n")
    else:
        result = live.query_table_assoc("GET eventconsolestatus\n")

    assert len(result) == 1

    status = result[0]

    for column_name in [
            'status_config_load_time',
            'status_num_open_events',
            'status_messages',
            'status_message_rate',
            'status_average_message_rate',
            'status_connects',
            'status_connect_rate',
            'status_average_connect_rate',
            'status_rule_tries',
            'status_rule_trie_rate',
            'status_average_rule_trie_rate',
            'status_drops',
            'status_drop_rate',
            'status_average_drop_rate',
            'status_events',
            'status_event_rate',
            'status_average_event_rate',
            'status_rule_hits',
            'status_rule_hit_rate',
            'status_average_rule_hit_rate',
            'status_average_processing_time',
            'status_average_request_time',
            'status_average_sync_time',
            'status_replication_slavemode',
            'status_replication_last_sync',
            'status_replication_success',
            'status_event_limit_host',
            'status_event_limit_rule',
            'status_event_limit_overall',
        ]:
        assert column_name in status

    assert type(status["status_event_limit_host"]) == int
    assert type(status["status_event_limit_rule"]) == int
    assert type(status["status_event_limit_overall"]) == int

# core == None means direct query to status socket
@pytest.mark.parametrize(("core"), [ None, "nagios", "cmc" ])
def test_rules_table_via_core(site, ec, core):
    print "Checking core: %s" % core

    live = ensure_core_and_get_connection(site, ec, core)
    if core == None:
        result = live.query_table_assoc("GET rules\n")
    else:
        result = live.query_table_assoc("GET eventconsolerules\n")

    assert type(result) == list
    #assert len(result) == 0
    # TODO: Add some rule before the test and then check the existing
    # keys and types in the result set
