'''
run manage.py flush to clean the database afterwards
'''
from django.core.management.base import BaseCommand
from kolibri.content import models

class Command(BaseCommand):
    help = 'To collect data for fixture, run the commandline $ kolibri manage dumpdata content'

    def populate_channel_db(self):
        '''populate ChannelMetadata'''
        channel_khan = models.ChannelMetadata.objects.create(name='khan', channel_id='6199dde6-95db-4ee4-ab39-2222d5af1e5c', author='eli', description='dummy khan', theme="i'm a json blob", subscribed=True)
        channel_ucsd = models.ChannelMetadata.objects.create(name='ucsd', channel_id='9788ab1e-eb91-4487-a2fb-89f9953e66ac', author='eli', description='dummy ucsd', theme="i'm a json blob", subscribed=True)

    def handle(self, *args, **options):
        self.populate_channel_db()