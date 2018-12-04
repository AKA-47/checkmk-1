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

import cmk.gui.config as config
import cmk.gui.i18n
from cmk.gui.i18n import _
from cmk.gui.permissions import (
    permission_section_registry,
    PermissionSection,
)

loaded_with_language = False

#   .----------------------------------------------------------------------.
#   |        ____                     _         _                          |
#   |       |  _ \ ___ _ __ _ __ ___ (_)___ ___(_) ___  _ __  ___          |
#   |       | |_) / _ \ '__| '_ ` _ \| / __/ __| |/ _ \| '_ \/ __|         |
#   |       |  __/  __/ |  | | | | | | \__ \__ \ | (_) | | | \__ \         |
#   |       |_|   \___|_|  |_| |_| |_|_|___/___/_|\___/|_| |_|___/         |
#   |                                                                      |
#   +----------------------------------------------------------------------+
#   | Declare general permissions for Multisite                            |
#   '----------------------------------------------------------------------'


@permission_section_registry.register
class PermissionSectionGeneral(PermissionSection):
    @property
    def name(self):
        return "general"

    @property
    def title(self):
        return _('General Permissions')

    @property
    def sort_index(self):
        return 10


def load_plugins(force):
    global loaded_with_language
    if loaded_with_language == cmk.gui.i18n.get_current_language() and not force:
        return

    config.declare_permission(
        "general.use",
        _("Use Multisite at all"),
        _("Users without this permission are not let in at all"),
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        "general.see_all",
        _("See all host and services"),
        _("See all objects regardless of contacts and contact groups. "
          "If combined with 'perform commands' then commands may be done on all objects."),
        ["admin", "guest"],
    )

    declare_visual_permissions('views', _("views"))
    declare_visual_permissions('dashboards', _("dashboards"))

    config.declare_permission(
        "general.view_option_columns",
        _("Change view display columns"),
        _("Interactively change the number of columns being displayed by a view (does not edit or customize the view)"
         ),
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        "general.view_option_refresh",
        _("Change view display refresh"),
        _("Interactively change the automatic browser reload of a view being displayed (does not edit or customize the view)"
         ),
        ["admin", "user"],
    )

    config.declare_permission(
        "general.painter_options",
        _("Change column display options"),
        _("Some of the display columns offer options for customizing their output. "
          "For example time stamp columns can be displayed absolute, relative or "
          "in a mixed style. This permission allows the user to modify display options"),
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        "general.act",
        _("Perform commands"),
        _("Allows users to perform Nagios commands. If no further permissions "
          "are granted, actions can only be done on objects one is a contact for"),
        ["admin", "user"],
    )

    config.declare_permission(
        "general.see_sidebar",
        _("Use Check_MK sidebar"),
        _("Without this permission the Check_MK sidebar will be invisible"),
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        "general.configure_sidebar",
        _("Configure sidebar"),
        _("This allows the user to add, move and remove sidebar snapins."),
        ["admin", "user"],
    )

    config.declare_permission(
        'general.edit_profile',
        _('Edit the user profile'),
        _('Permits the user to change the user profile settings.'),
        ['admin', 'user'],
    )

    config.declare_permission(
        "general.see_availability",
        _("See the availability"),
        _("See the availability views of hosts and services"),
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        "general.csv_export",
        _("Use CSV export"),
        _("Export data of views using the CSV export"),
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        'general.edit_notifications',
        _('Edit personal notification settings'),
        _('This allows a user to edit his personal notification settings. You also need the permission '
          '<i>Edit the user profile</i> in order to do this.'),
        ['admin', 'user'],
    )

    config.declare_permission(
        'general.disable_notifications',
        _('Disable all personal notifications'),
        _('This permissions provides a checkbox and timerange in the personal settings of the user that '
          'allows him to completely disable all of his notifications. Use with caution.'),
        ['admin'],
    )

    config.declare_permission(
        'general.edit_user_attributes',
        _('Edit personal user attributes'),
        _('This allows a user to edit his personal user attributes. You also need the permission '
          '<i>Edit the user profile</i> in order to do this.'),
        ['admin', 'user'],
    )

    config.declare_permission(
        'general.change_password',
        _('Edit the user password'),
        _('Permits the user to change the password.'),
        ['admin', 'user'],
    )

    config.declare_permission(
        'general.logout',
        _('Logout'),
        _('Permits the user to logout.'),
        ['admin', 'user', 'guest'],
    )

    config.declare_permission(
        "general.ignore_soft_limit",
        _("Ignore soft query limit"),
        _("Allows to ignore the soft query limit imposed upon the number of datasets returned by a query"
         ),
        ["admin", "user"],
    )

    config.declare_permission(
        "general.ignore_hard_limit",
        _("Ignore hard query limit"),
        _("Allows to ignore the hard query limit imposed upon the number of datasets returned by a query"
         ),
        ["admin"],
    )

    config.declare_permission(
        "general.acknowledge_werks",
        _("Acknowledge Incompatible Werks"),
        _("In the change log of the Check_MK software version the administrator can manage change log entries "
          "(Werks) that requrire user interaction. These <i>incompatible Werks</i> can be acknowledged only "
          "if the user has this permission."),
        ["admin"],
    )

    config.declare_permission(
        "general.see_failed_notifications_24h",
        _("See failed Notifications (last 24 hours)"),
        _("If Check_MK is unable to notify users about problems, the site will warn about this situation "
          "very visibly inside the UI (both in the Tactical Overview and the Dashboard). This affects only "
          "users with this permission. Users with this permission will only see failed notifications "
          "that occured within the last 24 hours."),
        ["user"],
    )

    config.declare_permission(
        "general.see_failed_notifications",
        _("See failed Notifications (all)"),
        _("If Check_MK is unable to notify users about problems, the site will warn about this situation "
          "very visibly inside the UI (both in the Tactical Overview and the Dashboard). This affects only "
          "users with this permission. Users with this permission will see failed notifications between now "
          "and the configured <a href=\"wato.py?mode=edit_configvar&varname=failed_notification_horizon\">Failed notification horizon</a>."
         ),
        ["admin"],
    )

    config.declare_permission(
        "general.see_stales_in_tactical_overview",
        _("See stale objects in tactical overview snapin"),
        _("Show the column for stale host and service checks in the tactical overview snapin."),
        ["guest", "user", "admin"],
    )

    config.declare_permission(
        "general.see_crash_reports",
        _("See crash reports"),
        _("In case an exception happens while Check_MK is running it may produce crash reports that you can "
          "use to track down the issues in the code or send it as report to the Check_MK team to fix this issue "
          "Only users with this permission are able to see the reports in the GUI."),
        ["admin"],
    )

    loaded_with_language = cmk.gui.i18n.get_current_language()


# TODO: This has been obsoleted by pagetypes.py
def declare_visual_permissions(what, what_plural):
    config.declare_permission(
        "general.edit_" + what,
        _("Customize %s and use them") % what_plural,
        _("Allows to create own %s, customize builtin %s and use them.") % (what_plural,
                                                                            what_plural),
        ["admin", "user"],
    )

    config.declare_permission(
        "general.publish_" + what,
        _("Publish %s") % what_plural,
        _("Make %s visible and usable for other users.") % what_plural,
        ["admin", "user"],
    )

    config.declare_permission(
        "general.publish_" + what + "_to_foreign_groups",
        _("Publish %s to foreign contact groups") % what_plural,
        _("Make %s visible and usable for users of contact groups the publishing user is not a member of."
         ) % what_plural,
        ["admin"],
    )

    config.declare_permission(
        "general.see_user_" + what,
        _("See user %s") % what_plural,
        _("Is needed for seeing %s that other users have created.") % what_plural,
        ["admin", "user", "guest"],
    )

    config.declare_permission(
        "general.force_" + what,
        _("Modify builtin %s") % what_plural,
        _("Make own published %s override builtin %s for all users.") % (what_plural, what_plural),
        ["admin"],
    )

    config.declare_permission(
        "general.edit_foreign_" + what,
        _("Edit foreign %s") % what_plural,
        _("Allows to edit %s created by other users.") % what_plural,
        ["admin"],
    )

    config.declare_permission(
        "general.delete_foreign_" + what,
        _("Delete foreign %s") % what_plural,
        _("Allows to delete %s created by other users.") % what_plural,
        ["admin"],
    )
