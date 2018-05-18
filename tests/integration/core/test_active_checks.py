#!/usr/bin/env python
# encoding: utf-8

import pytest

from testlib import web

import cmk_base.rulesets as rulesets

@pytest.fixture(scope="module")
def test_cfg(web, site):
    print "Applying default config"
    web.add_host("test-host", attributes={
        "ipaddress": "127.0.0.1",
        "tag_agent": "no-agent",
    })

    web.activate_changes()
    yield None

    #
    # Cleanup code
    #
    print "Cleaning up test config"

    web.delete_host("test-host")


@pytest.mark.parametrize(("core"), [ "nagios", "cmc" ])
def test_active_check_execution(test_cfg, site, web, core):
    site.set_config("CORE", core, with_restart=True)

    try:
        web.set_ruleset("custom_checks", {
            "ruleset": {
                # Main folder
                "": [
                    {
                        "value": {
                            'service_description': u'\xc4ctive-Check',
                            'command_line': 'echo "123"'
                        },
                        "conditions": {
                            "host_specs": rulesets.ALL_HOSTS,
                            "host_tags": [],
                        },
                        "options": {},
                    },
                ],
            }
        })
        web.activate_changes()

        site.schedule_check("test-host", u'\xc4ctive-Check', 0)

        result = site.live.query_row("GET services\nColumns: host_name description state plugin_output has_been_checked\nFilter: host_name = test-host\nFilter: description = Äctive-Check")
        assert result[4] == 1
        assert result[0] == "test-host"
        assert result[1] == u'\xc4ctive-Check'
        assert result[2] == 0
        assert result[3] == "123"
    finally:
        web.set_ruleset("custom_checks", {
            "ruleset": {
                "": [], # -> folder
            }
        })
        web.activate_changes()


@pytest.mark.parametrize(("core"), [ "nagios", "cmc" ])
def test_active_check_macros(test_cfg, site, web, core):
    site.set_config("CORE", core, with_restart=True)

    macros = {
        "$HOSTADDRESS$": "127.0.0.1",
        "$HOSTNAME$": "test-host",
        "$_HOSTTAGS$": "/wato/ ip-v4 ip-v4-only lan no-agent no-snmp ping prod site:%s wato" % site.id,
        "$_HOSTADDRESS_4$": "127.0.0.1",
        "$_HOSTADDRESS_6$": "",
        "$_HOSTADDRESS_FAMILY$": "4",
        "$USER1$": "/omd/sites/%s/lib/nagios/plugins" % site.id,
        "$USER2$": "/omd/sites/%s/local/lib/nagios/plugins" % site.id,
        "$USER3$": site.id,
        "$USER4$": site.root,
    }

    def descr(var):
        return "Macro %s" % var.strip("$")

    ruleset = []
    for var, value in macros.items():
        ruleset.append({
            "value": {
                'service_description': descr(var),
                'command_line': 'echo "Output: %s"' % var,
            },
            "conditions": {
                "host_specs": rulesets.ALL_HOSTS,
                "host_tags": [],
            },
        })

    try:
        web.set_ruleset("custom_checks", {
            "ruleset": {
                # Main folder
                "": ruleset,
            }
        })
        web.activate_changes()

        for var, value in macros.items():
            description = descr(var)
            site.schedule_check("test-host", description, 0)

            row = site.live.query_row(
                "GET services\n"
                "Columns: host_name description state plugin_output has_been_checked\n"
                "Filter: host_name = test-host\n"
                "Filter: description = %s\n" % description
            )

            name, description, state, plugin_output, has_been_checked = row

            assert name == "test-host"
            assert has_been_checked == 1
            assert state == 0

            expected_output = "Output: %s" % value
            # TODO: Cleanup difference between nagios/cmc
            if core == "nagios":
                expected_output = expected_output.strip()

            assert expected_output == plugin_output, \
                "Macro %s has wrong value (%r instead of %r)" % (var, plugin_output, expected_output)

    finally:
        web.set_ruleset("custom_checks", {
            "ruleset": {
                "": [], # -> folder
            }
        })
        web.activate_changes()
