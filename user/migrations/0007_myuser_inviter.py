# Generated by Django 5.0.3 on 2024-07-08 09:54

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0006_alter_myuser_avatar'),
    ]

    operations = [
        migrations.AddField(
            model_name='myuser',
            name='inviter',
            field=models.ForeignKey(db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL),
        ),
    ]
