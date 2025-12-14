# encoding: utf-8

import logging

from django.conf import settings
from django.db import ProgrammingError
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = ''
    help = 'Docker development environment entry point'

    def handle(self, *args, **options):
        from ...models import Clerk

        test = settings.DEBUG

        if not test:
            raise ValueError('Should run with DEBUG=true')

        try:
            Clerk.objects.first()
        except ProgrammingError:
            call_command('migrate')

            user, created = get_user_model().objects.get_or_create(
                username='mahti',
                defaults=dict(
                    is_superuser=True,
                    is_staff=True,
                    first_name='Markku',
                    last_name='Mahtinen',
                    email='mahti@example.com',
                ),
            )
            user.set_password("mahti")
            user.save()

            logger.log(
                logging.WARN if created else logging.DEBUG,
                'User %s %s',
                user,
                'created' if created else 'already exists'
            )

            call_command('loaddata', 'dev_data')

        call_command('runserver', '0.0.0.0:8000')
