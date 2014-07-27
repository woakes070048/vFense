import simplejson as json

import logging
import logging.config
from vFense import VFENSE_LOGGING_CONFIG
from vFense.core.api.base import BaseHandler
from vFense.core.view._constants import DefaultViews
from vFense.core.permissions._constants import Permissions
from vFense.core.permissions.decorators import check_permissions
from vFense.core.operations.decorators import log_operation
from vFense.core.operations._admin_constants import AdminActions
from vFense.core.operations._constants import vFenseObjects
from vFense.core.results import Results, ApiResultKeys
from vFense.core.tag.status_codes import (
    TagCodes, TagFailureCodes
)
from vFense.core.agent._constants import Environments
from vFense.core.agent.manager import AgentManager
from vFense.core.tag._db_model import TagKeys
from vFense.core.tag._db import fetch_agent_ids_in_tag
from vFense.core.tag import Tag
from vFense.core.view._db import token_exist_in_current
from vFense.core.tag.manager import TagManager
from vFense.core.tag.search.search import RetrieveTags
from vFense.core._constants import DefaultQueryValues, SortValues
from vFense.core.api._constants  import (
    ApiArguments, TagApiArguments, ApiValues
)
from vFense.core.decorators import (
    authenticated_request, convert_json_to_arguments, results_message
)
from vFense.core.user import UserKeys
from vFense.core.user.manager import UserManager
from vFense.plugins.patching.operations.store_operations import (
    StorePatchingOperation
)
from vFense.core.agent.operations.store_agent_operations import (
    StoreAgentOperations
)

logging.config.fileConfig(VFENSE_LOGGING_CONFIG)
logger = logging.getLogger('rvapi')


class TagsHandler(BaseHandler):
    @authenticated_request
    def get(self):
        active_user = self.get_current_user()
        active_view = (
            UserManager(active_user).get_attribute(UserKeys.CurrentView)
        )
        try:
            query = self.get_argument(ApiArguments.QUERY, None)
            count = int(
                self.get_argument(
                    ApiArguments.COUNT, DefaultQueryValues.COUNT
                )
            )
            offset = int(
                self.get_argument(
                    ApiArguments.OFFSET, DefaultQueryValues.OFFSET
                )
            )
            sort = (
                self.get_argument(
                    ApiArguments.SORT, DefaultQueryValues.SORT
                )
            )
            sort_by = (
                self.get_argument(ApiArguments.SORT_BY, TagKeys.TagName)
            )
            environment = (
                self.get_argument(TagApiArguments.ENVIRONMENT, None)
            )
            output = self.get_argument(ApiArguments.OUTPUT, 'json')

            search = (
                RetrieveTags(active_view, count, offset, sort, sort_by)
            )
            if not query and not environment:
                results = self.get_all_tags(search)

            elif query and not environment:
                results = self.get_all_tags_by_name(search, query)

            elif environment and not query:
                results = self.get_all_tags_by_prod_level(search, environment)

            elif query and environment:
                results = (
                    self.get_all_tags_by_prod_level_and_regex(
                        search, environment, query
                    )
                )

            self.set_status(results['http_status'])
            self.modified_output(results, output, 'tags')

        except Exception as e:
            data = {
                ApiResultKeys.MESSAGE: (
                    'Retrieving tags broke: {0}'.format(e)
                )
            }
            results = (
                Results(
                    active_user, self.request.uri, self.request.method
                ).something_broke(**data)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

    @results_message
    @check_permissions(Permissions.READ)
    def get_all_tags(self, search):
        results = search.all()
        return results

    @results_message
    @check_permissions(Permissions.READ)
    def get_all_tags_by_name(self, search, name):
        results = search.by_name(name)
        return results

    @results_message
    @check_permissions(Permissions.READ)
    def get_all_tags_by_env(self, search, environment):
        results = (
            search.by_key_val(search, TagKeys.Environment, environment)
        )
        return results

    @results_message
    @check_permissions(Permissions.READ)
    def get_all_tags_by_env_and_regex(self, search, environment, regex):
        results = (
            search.by_key_val_and_query(
                search, TagKeys.Environment, environment, regex
            )
        )
        return results

    @convert_json_to_arguments
    @authenticated_request
    def post(self):
        active_user = self.get_current_user()
        active_view = (
            UserManager(active_user).get_attribute(UserKeys.CurrentView)
        )
        try:
            tag_name = self.arguments.get(TagApiArguments.TAG_NAME)
            environment = (
                self.arguments.get(
                    TagApiArguments.ENVIRONMENT,
                    Environments.PRODUCTION
                )
            )
            if active_view == DefaultViews.GLOBAL:
                is_global = True
            else:
                is_global = False

            tag = Tag(tag_name, environment, active_view, is_global)
            results = self.create_tag(tag)

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            data = {
                ApiResultKeys.MESSAGE: (
                    'Create tag broke: {0}'.format(e)
                )
            }
            results = (
                Results(
                    active_user, self.request.uri, self.request.method
                ).something_broke(**data)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

    @results_message
    @check_permissions(Permissions.CREATE_TAG)
    @log_operation(AdminActions.CREATE_TAG, vFenseObjects.TAG)
    def create_tag(self, tag):
        manager = TagManager()
        results = manager.create(tag)
        return results

    @convert_json_to_arguments
    @authenticated_request
    def delete(self):
        active_user = self.get_current_user()
        try:
            tag_ids = self.arguments.get(TagApiArguments.TAG_IDS)
            results = self.remove_tags(tag_ids)

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            data = {
                ApiResultKeys.MESSAGE: (
                    'Delete tag broke: {0}'.format(e)
                )
            }
            results = (
                Results(
                    active_user, self.request.uri, self.request.method
                ).something_broke(**data)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

    @results_message
    @check_permissions(Permissions.REMOVE_TAG)
    @log_operation(AdminActions.REMOVE_TAGS, vFenseObjects.TAG)
    def remove_tags(self, tags):
        if not isinstance(tags, list):
            tags = tags.split()
        end_results = {}
        tags_deleted = []
        tags_unchanged = []
        for tag_id in tags:
            manager = TagManager(tag_id)
            results = manager.remove()
            if (results[ApiResultKeys.VFENSE_STATUS_CODE]
                    == TagCodes.TagsDeleted):
                tags_deleted.append(tag_id)
            else:
                tags_unchanged.append(tag_id)

        end_results[ApiResultKeys.UNCHANGED_IDS] = tags_unchanged
        end_results[ApiResultKeys.DELETED_IDS] = tags_deleted

        if tags_deleted and tags_unchanged:
            msg = (
                'Tags: {0} deleted and these tags didnt: {1}'
                .format(
                    ', '.join(tags_deleted),
                    ', '.join(tags_unchanged),
                )
            )
            end_results[ApiResultKeys.GENERIC_STATUS_CODE] = (
                TagFailureCodes.FailedToDeleteAllObjects
            )
            end_results[ApiResultKeys.VFENSE_STATUS_CODE] = (
                TagFailureCodes.FailedToDeleteTags
            )
            end_results[ApiResultKeys.MESSAGE] = msg

        elif tags_deleted and not tags_unchanged:
            msg = (
                'Tags: {0} deleted.'.format(', '.join(tags))
            )
            end_results[ApiResultKeys.GENERIC_STATUS_CODE] = (
                TagCodes.ObjectsDeleted
            )
            end_results[ApiResultKeys.VFENSE_STATUS_CODE] = (
                TagCodes.TagsDeleted
            )
            end_results[ApiResultKeys.MESSAGE] = msg

        elif tags_unchanged and not tags_deleted:
            msg = (
                'Tags: {0} failed to delete: {1}'
                .format(', '.join(tags), ', '.join(tags_unchanged))
            )
            end_results[ApiResultKeys.GENERIC_STATUS_CODE] = (
                TagCodes.ObjectsUnchanged
            )
            end_results[ApiResultKeys.VFENSE_STATUS_CODE] = (
                TagFailureCodes.FailedToDeleteTags
            )
            end_results[ApiResultKeys.MESSAGE] = msg

        return end_results

class TagHandler(BaseHandler):
    @authenticated_request
    def get(self, tag_id):
        active_user = self.get_current_user()
        active_view = (
            UserManager(active_user).get_attribute(UserKeys.CurrentView)
        )
        output = self.get_argument(ApiArguments.OUTPUT, 'json')
        search = RetrieveTags(active_view)
        results = self.get_tag(search, tag_id)
        self.set_status(results['http_status'])
        self.modified_output(results, output, 'tag')

    @results_message
    @check_permissions(Permissions.READ)
    def get_tag(self, search, tag_id):
        results = search.by_id(tag_id)
        return results


    @authenticated_request
    @convert_json_to_arguments
    def post(self, tag_id):
        active_user = self.get_current_user()
        active_view = (
            UserManager(active_user).get_attribute(UserKeys.CurrentView)
        )
        uri = self.request.uri
        http_method = self.request.method
        try:
            reboot = self.arguments.get(TagApiArguments.REBOOT, None)
            shutdown = self.arguments.get(TagApiArguments.SHUTDOWN, None)
            token = self.arguments.get(TagApiArguments.TOKEN, None)
            refresh_apps = (
                self.arguments.get(TagApiArguments.REFRESH_APPS, None)
            )
            operation = StoreAgentOperations(active_user, active_view)
            if reboot:
                results = (
                    self.reboot(operation, tag_id)
                )
            elif shutdown:
                results = self.shutdown(operation, tag_id)

            elif refresh_apps:
                operation = (
                    StorePatchingOperation(active_user, active_view)
                )
                results = self.apps_refresh(operation, tag_id)

            elif token:
                if token_exist_in_current(token):
                    results = self.assign_new_token(operation, tag_id, token)
                else:
                    msg = 'Invalid token {0}'.format(token)
                    result = Results(active_user, uri, http_method)
                    results = result.invalid_token(
                        **{
                            ApiResultKeys.INVALID_ID: token,
                            ApiResultKeys.MESSAGE: msg,
                        }
                    )

            else:
                data = {
                    ApiResultKeys.MESSAGE: (
                        'Invalid arguments on tag {0}'.format(tag_id)
                    )
                }
                results = (
                    Results(
                        active_user, self.request.uri, self.request.method
                    ).incorrect_arguments(**data)
                )

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            data = {
                ApiResultKeys.MESSAGE: (
                    'Agent operation for tag {0} broke: {1}'.format(tag_id, e)
                )
            }
            results = (
                Results(
                    active_user, self.request.uri, self.request.method
                ).something_broke(**data)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

    @results_message
    @check_permissions(Permissions.REBOOT)
    def reboot(self, operation, tag_id):
        results = operation.reboot(tag_id=tag_id)
        return results

    @results_message
    @check_permissions(Permissions.SHUTDOWN)
    def shutdown(self, operation, tag_id):
        results = operation.shutdown(tag_id=tag_id)
        return results

    @results_message
    @check_permissions(Permissions.READ)
    def apps_refresh(self, operation, tag_id):
        results = operation.apps_refresh(tag_id=tag_id)
        return results


    @results_message
    @check_permissions(Permissions.ASSIGN_NEW_TOKEN)
    @log_operation(AdminActions.ASSIGN_AGENT_TOKEN, vFenseObjects.TAG)
    def assign_new_token(self, operation, tag_id, token):
        agents = fetch_agent_ids_in_tag(tag_id)
        for agent in agents:
            manager = AgentManager(agent)
            manager.update_token(True)

        results = operation.new_token(agents, token=token)
        return results


    @convert_json_to_arguments
    @authenticated_request
    def put(self, tag_id):
        active_user = self.get_current_user()
        try:
            agent_ids = self.arguments.get('agent_ids', None)
            action = self.arguments.get(ApiArguments.ACTION, ApiValues.ADD)
            environment = (
                self.arguments.get(TagApiArguments.ENVIRONMENT, None)
            )
            manager = TagManager(tag_id)
            if agent_ids:
                if not isinstance(agent_ids, list):
                    agent_ids = agent_ids.split()

            if action == ApiValues.ADD and agent_ids and not environment:
                results = self.add_agents_to_tag(manager, agent_ids)
            elif action == ApiValues.DELETE and agent_ids and not environment:
                results = self.remove_agents_from_tag(manager, agent_ids)
            elif environment and not agent_ids:
                results = self.edit_environment(manager, environment)
            else:
                data = {
                    ApiResultKeys.MESSAGE: (
                        'Invalid arguments on tag {0}'.format(tag_id)
                    )
                }
                results = (
                    Results(
                        active_user, self.request.uri, self.request.method
                    ).incorrect_arguments(**data)
                )
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            data = {
                ApiResultKeys.MESSAGE: (
                    'Ediitng of tag {0} broke: {1}'.format(tag_id, e)
                )
            }
            results = (
                Results(
                    active_user, self.request.uri, self.request.method
                ).something_broke(**data)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

    @results_message
    @check_permissions(Permissions.ADD_AGENTS_TO_TAG)
    @log_operation(AdminActions.ADD_AGENTS_TO_TAG, vFenseObjects.TAG)
    def add_agents_to_tag(self, manager, agent_ids):
        if not isinstance(agent_ids, list):
            agent_ids = agent_ids.split()
        results = manager.add_agents(agent_ids)
        return results

    @results_message
    @check_permissions(Permissions.REMOVE_AGENTS_FROM_TAG)
    @log_operation(AdminActions.REMOVE_AGENTS_FROM_TAG, vFenseObjects.TAG)
    def remove_agents_from_tag(self, manager, agent_ids):
        if not isinstance(agent_ids, list):
            agent_ids = agent_ids.split()
        results = manager.remove_agents(agent_ids)
        return results

    @results_message
    @check_permissions(Permissions.EDIT_TAG)
    @log_operation(AdminActions.EDIT_TAG_ENVIRONMENT, vFenseObjects.TAG)
    def edit_environment(self, manager, environment):
        results = manager.edit_environment(environment)
        return results

    @convert_json_to_arguments
    @authenticated_request
    def delete(self, tag_id):
        active_user = self.get_current_user()
        try:
            manager = TagManager(tag_id)
            results = self.remove_tag(manager)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            data = {
                ApiResultKeys.MESSAGE: (
                    'Deleting of tag {0} broke:'.format(tag_id. e)
                )
            }
            results = (
                Results(
                    active_user, self.request.uri, self.request.method
                ).something_broke(**data)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

    @results_message
    @check_permissions(Permissions.REMOVE_TAG)
    @log_operation(AdminActions.REMOVE_TAG, vFenseObjects.TAG)
    def remove_tag(self, manager):
        results = manager.remove()
        return results