#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import time

from livestatus import MKLivestatusNotFoundError
import cmk.utils.render

from cmk.gui.globals import config
import cmk.gui.sites as sites
from cmk.gui.table import table_element
import cmk.gui.watolib as watolib
import cmk.gui.i18n
import cmk.gui.pages
from cmk.gui.i18n import _u, _
from cmk.gui.globals import html, request, transactions, user
from cmk.gui.utils.urls import makeactionuri
from cmk.gui.permissions import (
    permission_section_registry,
    PermissionSection,
    declare_permission,
)
from cmk.gui.page_menu import (
    PageMenu,
    PageMenuDropdown,
    PageMenuTopic,
    PageMenuEntry,
)
from cmk.gui.utils.flashed_messages import get_flashed_messages
from cmk.gui.breadcrumb import make_simple_page_breadcrumb
from cmk.gui.utils.urls import make_confirm_link
from cmk.gui.main_menu import mega_menu_registry
from cmk.gui.page_menu import make_simple_link

g_acknowledgement_time = {}
g_modified_time = 0.0
g_columns = ["time", "contact_name", "type", "host_name", "service_description", "comment"]


@permission_section_registry.register
class PermissionSectionNotificationPlugins(PermissionSection):
    @property
    def name(self):
        return "notification_plugin"

    @property
    def title(self):
        return _("Notification plugins")

    @property
    def do_sort(self):
        return True


# The permissions need to be loaded dynamically on each page load instead of
# only when the plugins need to be loaded because the user may have placed
# new notification plugins in the local hierarchy.
def load_plugins(force):
    for name, attrs in watolib.load_notification_scripts().items():
        if name[0] == ".":
            continue

        declare_permission("notification_plugin.%s" % name, _u(attrs["title"]), u"",
                           ["admin", "user"])


def acknowledge_failed_notifications(timestamp):
    g_acknowledgement_time[user.id] = timestamp
    user.acknowledged_notifications = int(g_acknowledgement_time[user.id])
    set_modified_time()


def set_modified_time():
    global g_modified_time
    g_modified_time = time.time()


def acknowledged_time():
    if g_acknowledgement_time.get(user.id) is None or\
            user.file_modified("acknowledged_notifications") > g_modified_time:
        g_acknowledgement_time[user.id] = user.acknowledged_notifications
        set_modified_time()
        if g_acknowledgement_time[user.id] == 0:
            # when this timestamp is first initialized, save the current timestamp as the acknowledge
            # date. This should considerably reduce the number of log files that have to be searched
            # when retrieving the list
            acknowledge_failed_notifications(time.time())

    return g_acknowledgement_time[user.id]


def load_failed_notifications(before=None, after=None, stat_only=False, extra_headers=None):
    may_see_notifications =\
        user.may("general.see_failed_notifications") or\
        user.may("general.see_failed_notifications_24h")

    if not may_see_notifications:
        return [0]

    query = ["GET log"]
    if stat_only:
        query.append("Stats: log_state != 0")
    else:
        query.append("Columns: %s" % " ".join(g_columns))
        query.append("Filter: log_state != 0")

    query.extend([
        "Filter: class = 3",
        "Filter: log_type = SERVICE NOTIFICATION RESULT",
        "Filter: log_type = HOST NOTIFICATION RESULT",
        "Or: 2",
    ])

    if before is not None:
        query.append("Filter: time <= %d" % before)
    if after is not None:
        query.append("Filter: time >= %d" % after)

    if may_see_notifications:
        if user.may("general.see_failed_notifications"):
            horizon = config.failed_notification_horizon
        else:
            horizon = 86400
        query.append("Filter: time > %d" % (int(time.time()) - horizon))

    query_txt = "\n".join(query)

    if extra_headers is not None:
        query_txt += extra_headers

    if stat_only:
        try:
            result = sites.live().query_summed_stats(query_txt)
        except MKLivestatusNotFoundError:
            result = [0]  # Normalize the result when no site answered

        if result[0] == 0 and not sites.live().dead_sites():
            # In case there are no errors and all sites are reachable:
            # advance the users acknowledgement time
            acknowledge_failed_notifications(time.time())

        return result

    return sites.live().query(query_txt)


def render_notification_table(failed_notifications):
    with table_element() as table:
        header = {name: idx for idx, name in enumerate(g_columns)}
        for row in failed_notifications:
            table.row()
            table.cell(_("Time"), cmk.utils.render.approx_age(time.time() - row[header['time']]))
            table.cell(_("Contact"), row[header['contact_name']])
            table.cell(_("Plugin"), row[header['type']])
            table.cell(_("Host"), row[header['host_name']])
            table.cell(_("Service"), row[header['service_description']])
            table.cell(_("Output"), row[header['comment']])


# TODO: We should really recode this to use the view and a normal view command / action
def render_page_confirm(acktime, failed_notifications):
    title = _("Confirm failed notifications")
    breadcrumb = make_simple_page_breadcrumb(mega_menu_registry.menu_monitoring(), title)

    confirm_url = make_simple_link(
        make_confirm_link(
            url=makeactionuri(request, transactions, [("acktime", str(acktime)),
                                                      ("_confirm", "1")]),
            message=_("Do you really want to acknowledge all failed notifications up to %s?") %
            cmk.utils.render.date_and_time(acktime),
        ))

    page_menu = PageMenu(
        dropdowns=[
            PageMenuDropdown(
                name="actions",
                title=_("Actions"),
                topics=[
                    PageMenuTopic(
                        title=_("Actions"),
                        entries=[
                            PageMenuEntry(
                                title=_("Confirm"),
                                icon_name="save",
                                item=confirm_url,
                                is_shortcut=True,
                                is_suggested=True,
                                is_enabled=failed_notifications,
                            ),
                        ],
                    ),
                ],
            ),
        ],
        breadcrumb=breadcrumb,
    )
    html.header(title, breadcrumb, page_menu)

    render_notification_table(failed_notifications)

    html.footer()


@cmk.gui.pages.register("clear_failed_notifications")
def page_clear():
    acktime = request.get_float_input_mandatory('acktime', time.time())
    if request.var('_confirm'):
        acknowledge_failed_notifications(acktime)

        if user.authorized_login_sites():
            watolib.init_wato_datastructures(with_wato_lock=True)

            title = _('Replicate user profile')
            breadcrumb = make_simple_page_breadcrumb(mega_menu_registry.menu_monitoring(), title)
            html.header(title, breadcrumb)

            for message in get_flashed_messages():
                html.show_message(message)
            # This local import is needed for the moment
            import cmk.gui.wato.user_profile  # pylint: disable=redefined-outer-name
            cmk.gui.wato.user_profile.user_profile_async_replication_page(
                back_url="clear_failed_notifications.py")
            return

    failed_notifications = load_failed_notifications(before=acktime, after=acknowledged_time())
    render_page_confirm(acktime, failed_notifications)
    if request.var('_confirm'):
        html.reload_whole_page()
