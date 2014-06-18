import logging

from vFense import VFENSE_LOGGING_CONFIG
from vFense.core.agent._db_model import *
from vFense.db.client import r
from vFense.plugins.patching._db_model import *
from vFense.plugins.patching._constants import CommonAppKeys
from vFense.core.agent.agents import get_all_agent_ids, get_agent_info
from vFense.core.tag._db_model import *
from vFense.plugins.patching._db_files import fetch_file_data
from vFense.plugins.patching.file_data import add_file_data

from vFense.plugins.patching._db import fetch_app_data, \
    fetch_apps_data_by_os_code, insert_app_data


logging.config.fileConfig(VFENSE_LOGGING_CONFIG)
logger = logging.getLogger('rvapi')


def add_custom_app_to_agents(username, view_name, uri, method,
                             file_data, agent_id=None, app_id=None):

    if app_id and not agent_id:
        app_info = (
            fetch_app_data(
                app_id, collection=AppCollections.CustomApps
            )
        )

        agent_ids = get_all_agent_ids(view_name, agent_os=app_info[AgentKeys.OsCode])
        if len(agent_ids) > 0:
            for agentid in agent_ids:
                add_file_data(app_id, file_data, agent_id)
                agent_info_to_insert = (
                    {
                        CustomAppsPerAgentKey.AgentId: agentid,
                        CustomAppsPerAgentKey.AppId: app_id,
                        CustomAppsPerAgentKey.Status: CommonAppKeys.AVAILABLE,
                        CustomAppsPerAgentKey.ViewName: view_name,
                        CustomAppsPerAgentKey.InstallDate: r.epoch_time(0.0)
                    }
                )
                insert_app_data(
                    agent_info_to_insert,
                    collection=AppCollections.CustomAppsPerAgent
                )

    if agent_id and not app_id:
        agent_info = get_agent_info(agent_id)
        apps_info = fetch_apps_data_by_os_code(
            agent_info[AgentKeys.OsCode], view_name,
            collection=AppCollections.CustomApps
        )

        for app_info in apps_info:
            app_id = app_info.get(CustomAppsKey.AppId)
            file_data = fetch_file_data(app_id)
            add_file_data(app_id, file_data, agent_id)

            agent_info_to_insert = {
                CustomAppsPerAgentKey.AgentId: agent_id,
                CustomAppsPerAgentKey.AppId: app_id,
                CustomAppsPerAgentKey.Status: CommonAppKeys.AVAILABLE,
                CustomAppsPerAgentKey.ViewName: view_name,
                CustomAppsPerAgentKey.InstallDate: r.epoch_time(0.0)
            }

            insert_app_data(
                agent_info_to_insert, collection=AppCollections.CustomAppsPerAgent
            )
