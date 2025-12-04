from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ("hybbconnect", "0002_ticket_reassigned_to_alter_ticket_concern_category_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='reassigned_to',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tickets_reassigned',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
