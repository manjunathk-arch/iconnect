from django.core.management.base import BaseCommand

from hybbconnect.attendance_movement import process_due_movements


class Command(BaseCommand):
    help = "Apply accepted employee location movements whose effective date has arrived."

    def handle(self, *args, **options):
        process_due_movements()
        self.stdout.write(self.style.SUCCESS("Due staff movements processed."))
