import logging as logger

from django.apps.registry import AppRegistryNotReady
try:
    from django.apps import apps
    apps.check_apps_ready()
except AppRegistryNotReady:
    import django; django.setup()

import requests
from django.core.management import call_command
from django.http import Http404
from django.utils.translation import ugettext as _
from django_q.humanhash import uuid
from kolibri.content.models import ChannelMetadataCache
from kolibri.content.utils.channels import get_mounted_drives_with_channel_info
from kolibri.content.utils.paths import get_content_database_file_url
from rest_framework import serializers, viewsets
from rest_framework.decorators import list_route
from rest_framework.response import Response

from multiprocessing import Process

logging = logger.getLogger(__name__)

def start_process_windows(channel_id, TASKTYPE, task_id):

    from django_q.tasks import async
    async(_networkimport, channel_id, sync=True, group=TASKTYPE, progress_updates=True, uuid=task_id)


class TasksViewSet(viewsets.ViewSet):

    def list(self, request):
        import django; django.setup()
        from django_q.models import Task
        tasks_response = [_task_to_response(t) for t in Task.objects.all()]
        return Response(tasks_response)

    def create(self, request):
        # unimplemented. Call out to the task-specific APIs for now.
        pass

    def retrieve(self, request, pk=None):
        import django; django.setup()
        from django_q.models import Task

        task = _task_to_response(Task.get_task(pk))
        return Response(task)

    def destroy(self, request, pk=None):
        # unimplemented for now.
        pass

    @list_route(methods=['post'])
    def startremoteimport(self, request):
        '''Download a channel's database from the main curation server, and then
        download its content.

        '''
        # Importing django/running setup because Windows...
        import django; django.setup()
        from django_q.models import Task
        TASKTYPE = "remoteimport"

        if "channel_id" not in request.data:
            raise serializers.ValidationError("The 'channel_id' field is required.")

        channel_id = request.data['channel_id']

        # ensure the requested channel_id can be found on the central server, otherwise error
        status = requests.head(get_content_database_file_url(channel_id)).status_code
        if status == 404:
            raise Http404(_("The requested channel does not exist on the content server."))

        task_id = uuid()

        task_process = Process(target=start_process_windows, args=(channel_id, TASKTYPE, task_id))
        task_process.start()

        # attempt to get the created Task, otherwise return pending status
        resp = _task_to_response(Task.get_task(task_id), task_type=TASKTYPE, task_id=task_id[1])

        return Response(resp)

    @list_route(methods=['post'])
    def startlocalimport(self, request):
        '''
        Import a channel from a local drive, and copy content to the local machine.

        '''
        # Importing django/running setup because Windows...
        TASKTYPE = "localimport"
        import django; django.setup()
        from django_q.models import Task

        if "drive_id" not in request.data:
            raise serializers.ValidationError("The 'drive_id' field is required.")

        task_id = async(_localimport, request.data['drive_id'], group=TASKTYPE, progress_updates=True)

        # attempt to get the created Task, otherwise return pending status
        resp = _task_to_response(Task.get_task(task_id), task_type=TASKTYPE, task_id=task_id)

        return Response(resp)

    @list_route(methods=['post'])
    def startlocalexport(self, request):
        '''
        Export a channel to a local drive, and copy content to the drive.

        '''
        TASKTYPE = "localexport"
        import django; django.setup()
        from django_q.models import Task

        if "drive_id" not in request.data:
            raise serializers.ValidationError("The 'drive_id' field is required.")

        task_id = async(_localexport, request.data['drive_id'], group=TASKTYPE, progress_updates=True)

        # attempt to get the created Task, otherwise return pending status
        resp = _task_to_response(Task.get_task(task_id), task_type=TASKTYPE, task_id=task_id)

        return Response(resp)

    @list_route(methods=['post'])
    def cleartask(self, request):
        '''
        Clears a task with its task id given in the task_id parameter.
        '''
        import django; django.setup()
        from django_q.models import Task, OrmQ

        if 'task_id' not in request.data:
            raise serializers.ValidationError("The 'task_id' field is required.")

        task_id = request.data['task_id']

        # we need to decrypt tasks first to get their real task_id. Hence why this python-side task_id retrieval and deletion.
        [taskitem.delete() for taskitem in OrmQ.objects.all() if taskitem.task()["id"] == task_id]

        Task.objects.filter(pk=task_id).delete()

        return Response({})

    @list_route(methods=['get'])
    def localdrive(self, request):
        drives = get_mounted_drives_with_channel_info()

        # make sure everything is a dict, before converting to JSON
        assert isinstance(drives, dict)
        out = [mountdata._asdict() for mountdata in drives.values()]

        return Response(out)

def _networkimport(channel_id, update_state=None):
    call_command("importchannel", "network", channel_id)
    call_command("importcontent", "network", channel_id, update_state=update_state)

def _localimport(drive_id, update_state=None):
    drives = get_mounted_drives_with_channel_info()
    drive = drives[drive_id]
    for channel in drive.metadata["channels"]:
        call_command("importchannel", "local", channel["id"], drive.datafolder)
        call_command("importcontent", "local", channel["id"], drive.datafolder, update_state=update_state)

def _localexport(drive_id, update_state=None):
    drives = get_mounted_drives_with_channel_info()
    drive = drives[drive_id]
    for channel in ChannelMetadataCache.objects.all():
        call_command("exportchannel", channel.id, drive.datafolder)
        call_command("exportcontent", channel.id, drive.datafolder, update_state=update_state)

def _task_to_response(task_instance, task_type=None, task_id=None):
    """"
    Converts a Task object to a dict with the attributes that the frontend expects.
    """

    if not task_instance:
        return {
            "type": task_type,
            "status": "PENDING",
            "percentage": 0,
            "progress": [],
            "id": task_id,
        }

    else:
        try:
            progress_data = iter(task_instance.progress_data)

            outputable_progress_data = []
            for p in progress_data:
                outputable_progress = p._asdict() if hasattr(p, '_asdict') else p.__dict__
                outputable_progress_data.append(outputable_progress)

            progress_data = outputable_progress_data
        except TypeError:   # progress_data not iterable, just return it
            progress_data = task_instance.progress_data

        return {
            "type": task_instance.group,
            "status": task_instance.task_status,
            "percentage": task_instance.progress_fraction,
            "progress": progress_data,
            "id": task_instance.id,
        }
