#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
"""Acknowledge problems

A problem occurs if a host is not UP or a service ist not OK.
The acknowledgement of the problem is the indication that the reported issue is known and that
somebody is attending to it.

You can find an introduction to the acknowledgement of problems in the
[Checkmk guide](https://docs.checkmk.com/latest/en/basics_ackn.html).
"""
# TODO: List acknowledgments
from urllib.parse import unquote

from cmk.gui import config, sites, http
from cmk.gui.plugins.openapi import fields
from cmk.gui.plugins.openapi.livestatus_helpers.commands.acknowledgments import (
    acknowledge_host_problem,
    acknowledge_hostgroup_problem,
    acknowledge_service_problem,
    acknowledge_servicegroup_problem,
)
from cmk.gui.plugins.openapi.livestatus_helpers.expressions import tree_to_expr
from cmk.gui.plugins.openapi.livestatus_helpers.queries import Query
from cmk.gui.plugins.openapi.livestatus_helpers.tables import Hosts, Services
from cmk.gui.plugins.openapi.restful_objects import (
    constructors,
    Endpoint,
    request_schemas,
)
from cmk.gui.plugins.openapi.utils import problem, ProblemException

SERVICE_DESCRIPTION = {
    'service_description': fields.String(
        description="The service description.",
        example="Memory",
    )
}


@Endpoint(constructors.collection_href('acknowledge', 'host'),
          'cmk/create',
          method='post',
          tag_group='Monitoring',
          additional_status_codes=[404],
          request_schema=request_schemas.AcknowledgeHostRelatedProblem,
          output_empty=True)
def set_acknowledgement_on_hosts(params):
    """Set acknowledgement on related hosts"""
    body = params['body']
    live = sites.live()

    sticky = body['sticky']
    notify = body['notify']
    persistent = body['persistent']
    comment = body['comment']

    acknowledge_type = body['acknowledge_type']

    if acknowledge_type == 'host':
        _set_acknowledgement_on_host(
            live,
            body['host_name'],
            sticky,
            notify,
            persistent,
            comment,
        )
    elif acknowledge_type == 'hostgroup':
        _set_acknowledgement_on_hostgroup(
            live,
            body['hostgroup_name'],
            sticky,
            notify,
            persistent,
            comment,
        )
    elif acknowledge_type == 'host_by_query':
        _set_acknowlegement_on_queried_hosts(
            live,
            body['query'],
            sticky,
            notify,
            persistent,
            comment,
        )
    else:
        return problem(status=400,
                       title="Unhandled acknowledge-type.",
                       detail=f"The acknowledge-type {acknowledge_type!r} is not supported.")

    return http.Response(status=204)


def _set_acknowledgement_on_host(
    connection,
    host_name: str,
    sticky: bool,
    notify: bool,
    persistent: bool,
    comment: str,
):
    """Acknowledge for a specific host"""
    host_state = Query([Hosts.state], Hosts.name == host_name).value(connection)

    if host_state > 0:
        acknowledge_host_problem(
            connection,
            host_name,
            sticky=sticky,
            notify=notify,
            persistent=persistent,
            user=config.user.ident,
            comment=comment,
        )


def _set_acknowlegement_on_queried_hosts(
    connection,
    query: str,
    sticky: bool,
    notify: bool,
    persistent: bool,
    comment: str,
):
    q = Query([Hosts.name]).filter(tree_to_expr(query, Hosts.__tablename__))
    hosts = q.fetchall(connection)

    if not hosts:
        raise ProblemException(status=404, title="The provided query returned no monitored hosts")

    for host in hosts:
        acknowledge_host_problem(
            connection,
            host.name,
            sticky=sticky,
            notify=notify,
            persistent=persistent,
            user=config.user.ident,
            comment=comment,
        )


def _set_acknowledgement_on_hostgroup(
    connection,
    hostgroup_name: str,
    sticky: bool,
    notify: bool,
    persistent: bool,
    comment: str,
):
    """Acknowledge for hosts of a host group"""
    acknowledge_hostgroup_problem(
        connection,
        hostgroup_name,
        sticky=sticky,
        notify=notify,
        persistent=persistent,
        user=config.user.ident,
        comment=comment,
    )


@Endpoint(constructors.collection_href('acknowledge', 'service'),
          'cmk/create_service',
          method='post',
          tag_group='Monitoring',
          additional_status_codes=[404, 422],
          request_schema=request_schemas.AcknowledgeServiceRelatedProblem,
          output_empty=True)
def set_acknowledgement_on_services(params):
    """Set acknowledgement on related services"""
    body = params['body']
    live = sites.live()

    sticky = body['sticky']
    notify = body['notify']
    persistent = body['persistent']
    comment = body['comment']

    acknowledge_type = body['acknowledge_type']

    if acknowledge_type == 'service':
        _set_acknowledgement_for_service(
            live,
            unquote(body['service_description']),
            sticky,
            notify,
            persistent,
            comment,
        )
    elif acknowledge_type == 'servicegroup':
        acknowledge_servicegroup_problem(
            live,
            body['servicegroup_name'],
            sticky=sticky,
            notify=notify,
            persistent=persistent,
            user=config.user.ident,
            comment=comment,
        )
    elif acknowledge_type == 'service_by_query':
        expr = tree_to_expr(body['query'], Services.__tablename__)
        q = Query([Services.host_name, Services.description, Services.state]).filter(expr)
        services = q.fetchall(live)
        if not services:
            return problem(
                status=422,
                title='No services with problems found.',
                detail='All queried services are OK.',
            )

        for service in services:
            if not service.state:
                continue
            acknowledge_service_problem(
                live,
                service.host_name,
                service.description,
                sticky=sticky,
                notify=notify,
                persistent=persistent,
                user=config.user.ident,
                comment=comment,
            )
    else:
        return problem(status=400,
                       title="Unhandled acknowledge-type.",
                       detail=f"The acknowledge-type {acknowledge_type!r} is not supported.")

    return http.Response(status=204)


def _set_acknowledgement_for_service(
    connection,
    service_description: str,
    sticky: bool,
    notify: bool,
    persistent: bool,
    comment: str,
):
    services = Query([Services.host_name, Services.description, Services.state],
                     Services.description == service_description).fetchall(connection)

    if not services:
        raise ProblemException(
            status=404,
            title=f'No services with {service_description!r} were found.',
        )

    for service in services:
        if not service.state:
            continue
        acknowledge_service_problem(
            connection,
            service.host_name,
            service.description,
            sticky=sticky,
            notify=notify,
            persistent=persistent,
            user=config.user.ident,
            comment=comment,
        )
